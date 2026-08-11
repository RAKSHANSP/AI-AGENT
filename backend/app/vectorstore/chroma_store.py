import os
import uuid
import logging
from typing import List, Any, Dict

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

from app.utils.pdf_loader import load_pdfs_from_directory
from app.utils.text_splitter import split_documents

logger = logging.getLogger(__name__)

class GeminiEmbeddingWrapper:
    """
    A wrapper class for Gemini API to generate embeddings, eliminating local model overhead.
    """
    def __init__(self):
        logger.info("Initializing Gemini Embeddings API Wrapper")
        
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        import google.generativeai as genai
        embeddings = []
        batch_size = 16
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            response = genai.embed_content(
                model="models/gemini-embedding-001",
                content=batch_texts,
                task_type="retrieval_document"
            )
            embeddings.extend(response['embedding'])
        return embeddings
        
    def embed_query(self, text: str) -> List[float]:
        import google.generativeai as genai
        response = genai.embed_content(
            model="models/gemini-embedding-001",
            content=text,
            task_type="retrieval_query"
        )
        return response['embedding']


class ChromaLangChainRetriever(BaseRetriever):
    """
    Custom LangChain Retriever to fetch top 5 context chunks from the local ChromaDB collection.
    """
    collection: Any = Field(description="ChromaDB Collection instance")
    embedder: Any = Field(description="GeminiEmbeddingWrapper instance")
    
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
    def __init__(self, db_path: str = "./chroma_db", collection_name: str = "startuptn_docs_gemini"):
        self.db_path = os.path.abspath(db_path)
        self.collection_name = collection_name
        
        # Initialize chroma client using registry/cache to prevent KeyError/concurrency issues
        global _CLIENTS
        if self.db_path not in _CLIENTS:
            os.makedirs(self.db_path, exist_ok=True)
            _CLIENTS[self.db_path] = chromadb.PersistentClient(path=self.db_path)
        self.client = _CLIENTS[self.db_path]
        
        # Initialize Embeddings model wrapper
        self.embedder = GeminiEmbeddingWrapper()
        
        # Get or create persistent collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"Initialized ChromaDB at {self.db_path} with collection: {collection_name}")

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
            "total_chunks_added": 0
        }
        
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
                    # 1. Load single document
                    docs = load_pdfs_from_directory(data_dir)
                    # Filter documents to only include the current file
                    file_docs = [d for d in docs if d.metadata.get("source") == filename]
                    
                    if not file_docs:
                        logger.warning(f"No text extracted from {filename}")
                        continue
                        
                    # 2. Split single document
                    chunks = split_documents(file_docs)
                    if not chunks:
                        continue
                        
                    # 3. Add to Chroma
                    texts = [c.page_content for c in chunks]
                    metadatas = [c.metadata for c in chunks]
                    embeddings = self.embedder.embed_documents(texts)
                    ids = [f"{filename}_{uuid.uuid4()}" for _ in chunks]
                    
                    self.collection.add(
                        ids=ids,
                        embeddings=embeddings,
                        metadatas=metadatas,
                        documents=texts
                    )
                    
                    stats["indexed"].append(filename)
                    stats["total_chunks_added"] += len(chunks)
                    logger.info(f"Successfully indexed {filename} ({len(chunks)} chunks).")
                except Exception as e:
                    logger.error(f"Failed to index {filename}: {str(e)}")
        else:
            logger.info("No new documents to index. ChromaDB is up to date.")
            
        return stats

    def get_retriever(self) -> BaseRetriever:
        """
        Returns a LangChain compatible retriever for RAG.
        """
        return ChromaLangChainRetriever(collection=self.collection, embedder=self.embedder)
