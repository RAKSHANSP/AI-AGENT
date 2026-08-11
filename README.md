# StartupTN AI Assistant

StartupTN AI Assistant is a production-grade, web-based Retrieval-Augmented Generation (RAG) chatbot application. It reads official PDFs containing StartupTN guidelines, MSME schemes, and DPIIT benefits, processes and indexes them using a local vector store, and utilizes Google's Gemini LLM to answer user inquiries accurately and with source citations.

The application is split into a **FastAPI Backend** and a **React.js Frontend** (scaffolded with Vite).

---

## Project Structure

```text
StartupTN-Chatbot/ (Workspace Root)
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI Application Entry
│   │   ├── services/
│   │   │   └── gemini_service.py   # Gemini API and LangChain configuration
│   │   ├── utils/
│   │   │   ├── pdf_loader.py       # PDF Text Extractor (PyPDF)
│   │   │   └── text_splitter.py    # Recursive splitter for chunks
│   │   └── vectorstore/
│   │       └── chroma_store.py     # Embeddings (SentenceTransformers) & Chroma DB
│   ├── data/                       # Directory containing source PDFs
│   ├── chroma_db/                  # Automatically created ChromaDB folder
│   ├── requirements.txt            # Python dependencies
│   └── .env                        # System settings and Gemini API key
│
├── frontend/
│   ├── src/
│   │   ├── services/
│   │   │   └── api.js              # Centralized Axios API service
│   │   ├── App.css                 # Premium custom layout stylesheet
│   │   ├── App.jsx                 # Primary Chat and Admin Interface
│   │   ├── index.css               # Global reset & CSS variables
│   │   └── main.jsx
│   ├── index.html                  # HTML entry point (contains metadata and fonts)
│   ├── package.json                # React NPM dependencies
│   ├── vite.config.js              # Vite React configuration
│   └── .env                        # Frontend environment settings (VITE_API_BASE_URL)
│
└── README.md                       # This runner guide
```

---

## Prerequisites

1. Ensure you have Node.js (v18+) and Python (v3.10+) installed.
2. Place your StartupTN PDF documents inside the `backend/data/` folder.
3. Configure your API key inside `backend/.env`. (Note: If it contains only the raw Gemini API key, the service will load it automatically, but the recommended format is: `GEMINI_API_KEY=your_actual_key`).
4. Set an administrative password in `backend/.env` for admin functions (Defaults to `admin123` if not configured):
   ```env
   ADMIN_PASSWORD=your_custom_admin_password
   ```

---

## Run the Application

The application is run as two separate services:

### 1. Start the FastAPI Backend

Open a terminal at the project root and execute the following:

```bash
# Activate the pre-configured virtual environment
source venv/bin/activate

# Install backend dependencies
pip install -r backend/requirements.txt

# Run the FastAPI server (launches on http://localhost:8000)
cd backend
python -m uvicorn app.main:app --reload
```

---

### 2. Start the React Frontend

Open a second terminal at the project root and execute:

```bash
# Navigate to the frontend directory
cd frontend

# Install package dependencies
npm install

# Run the Vite development server (launches on http://localhost:5173)
npm run dev
```

Open your browser and navigate to `http://localhost:5173/` to interact with the assistant.

---

## Features & Usage

### User Chat Assistant
- **Suggested Questions**: Click on any of the suggested questions to instantly run inquiries.
- **Smart Citations**: When the assistant answers questions, it lists the source document names that contributed to the answer.
- **Clear Chat**: Click **Clear Chat** in the header to wipe current session state.

### Administrative Management Panel
- **Access**: Click **Admin Area** in the bottom-left sidebar, enter the administrative password (default `admin123`), and verify credentials.
- **Ingestion & Sync**: 
  - Scan the local folder and update the vector index instantly by clicking **Sync Index** (or **Sync Local PDFs** from the main sidebar footer when logged in).
  - Drag and drop or browse to upload new PDFs directly via the Web UI.
- **Purge Documents**: Remove stale files from the knowledge base by clicking the trash icon next to documents in the manager. Purging will trigger database rebuilds automatically.
