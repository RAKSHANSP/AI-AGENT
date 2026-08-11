import os
import shutil
import logging
from typing import List, Dict, Any
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Header
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
# Allow localhost:5173 (standard Vite development server origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths configuration
DATA_DIR = os.path.join(backend_root, "data")
DB_PATH = os.path.join(backend_root, "chroma_db")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DB_PATH, exist_ok=True)

# Global variables for RAG services
vector_store = None
rag_pipeline = None

# Admin token configuration
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
MOCK_TOKEN = "startuptn-secure-admin-token"

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
    try:
        # Initialize Vector Store
        vector_store = StartupTNVectorStore(db_path=DB_PATH)
        # Perform initial sync with local data directory
        vector_store.sync_database(data_dir=DATA_DIR)
        
        # Initialize LangChain RAG pipeline
        rag_pipeline = GeminiRAGPipeline(vector_store.get_retriever())
        logger.info("Startup initialization complete.")
    except Exception as e:
        logger.error(f"Startup initialization failed: {str(e)}")

@app.get("/")
def read_root():
    return {"status": "online", "message": "StartupTN AI Assistant backend is running."}

@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    if not rag_pipeline:
        raise HTTPException(status_code=503, detail="RAG Pipeline not initialized")
    
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
        
    try:
        answer, sources = rag_pipeline.run_query(question)
        return ChatResponse(answer=answer, sources=sources)
    except Exception as e:
        logger.error(f"Error handling query: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Query Error: {str(e)}")

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
        return {
            "files_count": len(indexed_files),
            "chunks_count": doc_count,
            "indexed_files": indexed_files
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
