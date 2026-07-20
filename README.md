# StartupTN AI Assistant

StartupTN AI Assistant is a production-grade Retrieval-Augmented Generation (RAG) chatbot application. It reads official PDFs containing StartupTN guidelines, MSME schemes, and DPIIT benefits, processes and indexes them using a local vector store, and utilizes Google's Gemini LLM to answer user inquiries accurately and with source citations.

## Project Structure

```text
StartupTN-Chatbot/
├── app.py                  # Main Streamlit Application
├── requirements.txt        # Python dependency list
├── README.md               # User guide and setup instructions
├── .env                    # System configuration file (contains GEMINI_API_KEY)
├── data/                   # Directory containing source PDFs (DPIIT, msme schemes, hubs etc.)
├── chroma_db/              # Directory created automatically to store ChromaDB indices
├── services/
│   ├── __init__.py
│   └── gemini_service.py   # Configures Gemini API and sets up the LangChain pipeline
├── utils/
│   ├── __init__.py
│   ├── pdf_loader.py       # Reads PDF files and parses text page-by-page using PyPDF
│   └── text_splitter.py    # Chunks extracted text using RecursiveCharacterTextSplitter
└── vectorstore/
    ├── __init__.py
    └── chroma_store.py     # Coordinates SentenceTransformers embeddings and ChromaDB operations
```

## Features

- **Automated Scanning & Synchronization**: Scans the `data/` folder automatically and indexes documents.
- **Smart Persistent Indexing**: Chunks and indexes PDFs into a persistent ChromaDB database, meaning it loads instantly without re-processing large PDFs on every app restart.
- **LangChain RAG Pipeline**: Combines semantic search with the Gemini API to formulate factual answers.
- **Failsafe System**: If the retrieved documents do not contain relevant information, it responds with the exact fallback text: *"I couldn't find this information in the StartupTN knowledge base."*
- **Source Citations**: Lists the source documents used to build the answer directly below the response.
- **Interactive UI**: Custom ChatGPT-style dark mode dashboard with Suggested Questions, Clear Chat, and database health metrics.

---

## Getting Started

### 1. Prerequisite Setup

Make sure your `data/` folder contains your StartupTN PDF documents, and your `.env` contains your Google Gemini API Key in this format:

```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

### 2. Activate the Virtual Environment

Ensure you activate the pre-configured virtual environment:

```bash
source venv/bin/activate
```

### 3. Install Dependencies

Install the required packages in your environment:

```bash
pip install -r requirements.txt
```

### 4. Run the Chatbot

Start the Streamlit application:

```bash
streamlit run app.py
```

Streamlit will print the local URL (usually `http://localhost:8501`). Open this in your web browser.

---

## Ingestion and In-App Synchronization

On the first launch, the app automatically processes all PDFs in the `data/` folder and loads them into ChromaDB.
If you add new PDFs to `data/` or delete existing ones, click the **🔄 Sync Local PDFs** button in the sidebar. This will instantly refresh the database without restarting the app.
To wipe the conversation history, click the **🗑️ Clear Conversation History** button.
