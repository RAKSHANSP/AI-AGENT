import os
import shutil
import logging
import asyncio
import time
from typing import List, Dict, Any
import json
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Import existing RAG components
from app.vectorstore.chroma_store import StartupTNVectorStore
from app.services.gemini_service import GeminiRAGPipeline

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load env variables
# Load from root/backend/.env
backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(backend_root, ".env")
load_dotenv(dotenv_path=env_path)

# Initialize FastAPI App
app = FastAPI(title="StartupTN AI Assistant API", version="1.0.0")

# Setup CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths configuration
DATA_DIR = os.getenv("DATA_DIR", os.path.join(backend_root, "data"))
DB_PATH = os.getenv("DB_PATH", os.path.join(backend_root, "chroma_db"))

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DB_PATH, exist_ok=True)

# Global variables for RAG services
vector_store = None
rag_pipeline = None

# Admin token configuration
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
MOCK_TOKEN = "startuptn-secure-admin-token"

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

# Schema models
class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str
    sources: List[str]

class LoginRequest(BaseModel):
    password: str

# Helper dependency to check authorization token
def verify_admin_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication token missing")
    token = authorization.replace("Bearer ", "").strip()
    if token != MOCK_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid administration token")
    return True

@app.on_event("startup")
async def startup_event():
    global vector_store, rag_pipeline
    logger.info("Initializing vector store and RAG pipeline...")
    _debug_log("main.py:startup:begin", "Startup began", {"data_dir": DATA_DIR}, "C")
    try:
        vector_store = StartupTNVectorStore(db_path=DB_PATH)
        rag_pipeline = GeminiRAGPipeline(vector_store.get_retriever())
        _debug_log("main.py:startup:ready", "RAG pipeline ready before sync", {
            "chunk_count": vector_store.get_document_count(),
        }, "C")

        async def background_sync():
            try:
                stats = vector_store.sync_database(data_dir=DATA_DIR)
                _debug_log("main.py:startup:sync_done", "Background sync complete", {
                    "indexed": stats.get("indexed", []),
                    "total_chunks_added": stats.get("total_chunks_added", 0),
                    "errors": [{"file": e["file"], "error": e["error"][:120]} for e in stats.get("errors", [])],
                    "pdfs_on_disk": stats.get("pdfs_on_disk", 0),
                }, "A")
            except Exception as sync_err:
                logger.error(f"Background sync failed: {str(sync_err)}")
                _debug_log("main.py:startup:sync_error", "Background sync failed", {"error": str(sync_err)}, "A")

        asyncio.create_task(background_sync())
        logger.info("Startup initialization complete.")
    except Exception as e:
        logger.error(f"Startup initialization failed: {str(e)}")
        _debug_log("main.py:startup:error", "Startup failed", {"error": str(e)}, "C")

@app.get("/")
def read_root():
    return {"status": "online", "message": "StartupTN AI Assistant backend is running."}

@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    _debug_log("main.py:chat:request", "Chat request received", {
        "rag_ready": rag_pipeline is not None,
        "question_len": len(request.question or ""),
    }, "B,C")
    if not rag_pipeline:
        _debug_log("main.py:chat:503", "RAG pipeline not ready", {}, "C")
        raise HTTPException(status_code=503, detail="RAG Pipeline not initialized")
    
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
        
    def sse_generator():
        try:
            for event in rag_pipeline.run_query_stream(question):
                if event.get("type") == "error":
                    _debug_log("main.py:chat:sse_error", "Gemini/stream error in SSE", {
                        "content_preview": str(event.get("content", ""))[:200],
                    }, "B")
                yield f"data: {json.dumps(event)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Error in streaming query: {str(e)}")
            _debug_log("main.py:chat:exception", "Streaming exception", {"error": str(e)}, "B")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.post("/api/admin/login")
def admin_login(request: LoginRequest):
    if request.password == ADMIN_PASSWORD:
        return {"token": MOCK_TOKEN}
    else:
        raise HTTPException(status_code=401, detail="Invalid password")

@app.get("/api/admin/status")
def get_admin_status():
    if not vector_store:
        raise HTTPException(status_code=503, detail="Vector Store not initialized")
    try:
        doc_count = vector_store.get_document_count()
        indexed_files = vector_store.get_indexed_files()
        disk_pdfs = []
        if os.path.exists(DATA_DIR):
            disk_pdfs = [f for f in os.listdir(DATA_DIR) if f.lower().endswith(".pdf")]
        return {
            "files_count": len(indexed_files),
            "chunks_count": doc_count,
            "indexed_files": indexed_files,
            "pdfs_on_disk": len(disk_pdfs),
            "disk_files": sorted(disk_pdfs),
        }
    except Exception as e:
        logger.error(f"Error fetching database stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/upload")
async def upload_document(file: UploadFile = File(...), authorized: bool = Depends(verify_admin_token)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
    file_path = os.path.join(DATA_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"File uploaded: {file.filename}")
        return {"status": "success", "message": f"Successfully uploaded {file.filename}."}
    except Exception as e:
        logger.error(f"Failed to upload document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/api/admin/sync")
def sync_database_endpoint(authorized: bool = Depends(verify_admin_token)):
    if not vector_store:
        raise HTTPException(status_code=503, detail="Vector Store not initialized")
    try:
        logger.info("Manual synchronization triggered.")
        sync_stats = vector_store.sync_database(data_dir=DATA_DIR)
        return {"status": "success", "sync_stats": sync_stats}
    except Exception as e:
        logger.error(f"Synchronization failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@app.delete("/api/admin/documents/{filename}")
def delete_document(filename: str, authorized: bool = Depends(verify_admin_token)):
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        # 1. Delete file from filesystem
        os.remove(file_path)
        logger.info(f"File removed from storage: {filename}")
        
        # 2. Sync database to automatically purge embeddings for this file
        sync_stats = vector_store.sync_database(data_dir=DATA_DIR)
        
        return {
            "status": "success", 
            "message": f"Successfully deleted {filename} from storage and index.",
            "sync_stats": sync_stats
        }
    except Exception as e:
        logger.error(f"Failed to delete document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")
