import os
import uuid
import json
import time
import gc
import logging
from typing import List, Any, Dict, Optional

EMBED_BATCH_SIZE = 8

DEBUG_LOG_PATH = "/home/rakshan/Desktop/StartupTN-Chatbot/.cursor/debug-0faf1f.log"

def _debug_log(location: str, message: str, data: dict, hypothesis_id: str):
    # #region agent log
    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "sessionId": "0faf1f",
                "location": location,
                "message": message,
                "data": data,
                "timestamp": int(time.time() * 1000),
                "hypothesisId": hypothesis_id,
            }) + "\n")
    except Exception:
        pass
    # #endregion

# Monkey-patch chromadb's rust bindings stop method to prevent AttributeError during hot-reloading
try:
    import chromadb.api.rust
    def safe_stop(self):
        if hasattr(self, "bindings"):
            try:
                del self.bindings
            except AttributeError:
                pass
    chromadb.api.rust.RustBindingsAPI.stop = safe_stop
except Exception:
    pass

import chromadb
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from app.utils.pdf_loader import load_single_pdf
from app.utils.text_splitter import split_documents

logger = logging.getLogger(__name__)

class LocalEmbeddingWrapper:
    """
    Local embeddings via FastEmbed — no Gemini API quota needed for indexing.
    Loaded lazily on first use to keep Render startup under 512MB.
    """
    _model = None

    def _ensure_model(self):
        if LocalEmbeddingWrapper._model is None:
            from fastembed import TextEmbedding
            logger.info("Loading local FastEmbed model (BAAI/bge-small-en-v1.5)")
            LocalEmbeddingWrapper._model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        return LocalEmbeddingWrapper._model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        model = self._ensure_model()
        return [[float(x) for x in vec] for vec in model.embed(texts)]

    def embed_query(self, text: str) -> List[float]:
        model = self._ensure_model()
        return [float(x) for x in next(model.embed([text]))]


class ChromaLangChainRetriever(BaseRetriever):
    """
    Custom LangChain Retriever to fetch top 5 context chunks from the local ChromaDB collection.
    """
    collection: Any = Field(description="ChromaDB Collection instance")
    embedder: Any = Field(description="LocalEmbeddingWrapper instance")
    
    def _get_relevant_documents(self, query: str, *, run_manager=None) -> List[Document]:
        try:
            query_embedding = self.embedder.embed_query(query)
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=5
            )
            
            documents = []
            if results and "documents" in results and results["documents"]:
                retrieved_docs = results["documents"][0]
                retrieved_metadatas = results["metadatas"][0] if "metadatas" in results else [{}] * len(retrieved_docs)
                
                for doc_text, metadata in zip(retrieved_docs, retrieved_metadatas):
                    documents.append(Document(page_content=doc_text, metadata=metadata))
            return documents
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {str(e)}")
            return []


_CLIENTS = {}

class StartupTNVectorStore:
    """
    Manages the persistent ChromaDB database, handling PDF loading, splitting, 
    indexing, and retrieval of documents.
    """
    def __init__(self, db_path: str = "./chroma_db", collection_name: str = "startuptn_docs_bge"):
        self.db_path = os.path.abspath(db_path)
        self.collection_name = collection_name
        
        # Initialize chroma client using registry/cache to prevent KeyError/concurrency issues
        global _CLIENTS
        if self.db_path not in _CLIENTS:
            os.makedirs(self.db_path, exist_ok=True)
            _CLIENTS[self.db_path] = chromadb.PersistentClient(path=self.db_path)
        self.client = _CLIENTS[self.db_path]

        # Lazy — model loads on first embed (saves ~200MB during Render boot)
        self._embedder: Optional[LocalEmbeddingWrapper] = None

        # Get or create persistent collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"Initialized ChromaDB at {self.db_path} with collection: {collection_name}")

    @property
    def embedder(self) -> LocalEmbeddingWrapper:
        if self._embedder is None:
            self._embedder = LocalEmbeddingWrapper()
        return self._embedder

    def _index_file_in_batches(self, filename: str, chunks: List[Document]) -> int:
        """Embed and store chunks in small batches to stay within Render 512MB limit."""
        added = 0
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[i:i + EMBED_BATCH_SIZE]
            texts = [c.page_content for c in batch]
            metadatas = [c.metadata for c in batch]
            embeddings = self.embedder.embed_documents(texts)
            ids = [f"{filename}_{uuid.uuid4()}" for _ in batch]
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=texts,
            )
            added += len(batch)
        return added

    def get_indexed_files(self) -> List[str]:
        """
        Retrieves names of all unique source PDF files currently stored in ChromaDB.
        """
        try:
            # Query the first 10000 records to extract unique file names
            results = self.collection.get(include=["metadatas"])
            if not results or not results.get("metadatas"):
                return []
            
            unique_sources = set()
            for meta in results["metadatas"]:
                if meta and "source" in meta:
                    unique_sources.add(meta["source"])
            return list(unique_sources)
        except Exception as e:
            logger.error(f"Error getting indexed files: {str(e)}")
            return []

    def get_document_count(self) -> int:
        """
        Returns total number of chunks currently stored in the collection.
        """
        return self.collection.count()

    def sync_database(self, data_dir: str = "./data") -> Dict[str, Any]:
        """
        Synchronizes the persistent database with the local PDFs in data_dir.
        Loads, splits, and embeds any new PDFs. Deletes embeddings for removed PDFs.
        
        Returns:
            Dict: Ingestion statistics (indexed, skipped, deleted files)
        """
        if not os.path.exists(data_dir):
            logger.warning(f"Data directory '{data_dir}' not found. Cannot sync.")
            return {"status": "error", "message": f"Data directory '{data_dir}' not found."}
            
        current_pdfs = [f for f in os.listdir(data_dir) if f.lower().endswith(".pdf")]
        indexed_pdfs = self.get_indexed_files()
        
        to_index = [f for f in current_pdfs if f not in indexed_pdfs]
        to_delete = [f for f in indexed_pdfs if f not in current_pdfs]
        
        stats = {
            "indexed": [],
            "deleted": [],
            "skipped": [f for f in current_pdfs if f in indexed_pdfs],
            "errors": [],
            "total_chunks_added": 0,
            "pdfs_on_disk": len(current_pdfs),
            "pdfs_indexed_before": len(indexed_pdfs),
        }

        _debug_log("chroma_store.py:sync:start", "Sync started", {
            "data_dir": data_dir,
            "current_pdfs": current_pdfs,
            "indexed_pdfs": indexed_pdfs,
            "to_index": to_index,
        }, "A")
        
        # Handle deletions
        for filename in to_delete:
            logger.info(f"Removing stale file from index: {filename}")
            try:
                self.collection.delete(where={"source": filename})
                stats["deleted"].append(filename)
            except Exception as e:
                logger.error(f"Failed to delete {filename} from index: {str(e)}")
                
        # Handle new indexings
        if to_index:
            logger.info(f"Indexing new PDF files: {to_index}")
            for filename in to_index:
                file_path = os.path.join(data_dir, filename)
                try:
                    file_docs = load_single_pdf(file_path, filename)

                    if not file_docs:
                        logger.warning(f"No text extracted from {filename}")
                        continue

                    chunks = split_documents(file_docs)
                    if not chunks:
                        continue

                    added = self._index_file_in_batches(filename, chunks)
                    stats["indexed"].append(filename)
                    stats["total_chunks_added"] += added
                    logger.info(f"Successfully indexed {filename} ({added} chunks).")
                    gc.collect()
                except Exception as e:
                    err_msg = str(e)
                    logger.error(f"Failed to index {filename}: {err_msg}")
                    stats["errors"].append({"file": filename, "error": err_msg})
        else:
            logger.info("No new documents to index. ChromaDB is up to date.")

        _debug_log("chroma_store.py:sync:done", "Sync finished", {
            "indexed": stats["indexed"],
            "deleted": stats["deleted"],
            "skipped": stats["skipped"],
            "errors": [{"file": e["file"], "error": e["error"][:200]} for e in stats["errors"]],
            "total_chunks_added": stats["total_chunks_added"],
            "pdfs_on_disk": stats["pdfs_on_disk"],
        }, "A")
        return stats

    def get_retriever(self) -> BaseRetriever:
        """
        Returns a LangChain compatible retriever for RAG.
        """
        return ChromaLangChainRetriever(collection=self.collection, embedder=self.embedder)
