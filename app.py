import streamlit as st
import os
import time
import logging
from vectorstore.chroma_store import StartupTNVectorStore
from services.gemini_service import GeminiRAGPipeline

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="StartupTN AI Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium CSS to inject
st.markdown("""
<style>
    /* Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;600;800&display=swap');
    
    /* Core background */
    .stApp {
        background-color: #0b0f19;
        font-family: 'Inter', sans-serif;
    }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #0d1224 !important;
        border-right: 1px solid rgba(99, 102, 241, 0.15) !important;
        padding-top: 2rem;
    }
    
    /* Custom Titles styling */
    .brand-title {
        font-family: 'Outfit', sans-serif;
        background: linear-gradient(135deg, #818cf8 0%, #c084fc 50%, #f472b6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 2.2rem;
        margin-bottom: 0.5rem;
        text-align: center;
    }
    
    .brand-subtitle {
        font-family: 'Inter', sans-serif;
        color: #9ca3af;
        font-size: 0.95rem;
        text-align: center;
        margin-bottom: 2rem;
        font-weight: 400;
    }
    
    /* Sidebar titles */
    .sidebar-section-title {
        font-family: 'Outfit', sans-serif;
        color: #e5e7eb;
        font-size: 1.1rem;
        font-weight: 600;
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        padding-bottom: 0.25rem;
    }
    
    /* Chat elements wrapper */
    .chat-container {
        max-width: 800px;
        margin: 0 auto;
        padding: 2rem 1rem;
    }
    
    /* Source Tags container and chips */
    .source-container {
        display: flex;
        flex-wrap: wrap;
        margin-top: 0.75rem;
        padding-top: 0.5rem;
        border-top: 1px dashed rgba(255, 255, 255, 0.08);
    }
    
    .source-chip {
        display: inline-flex;
        align-items: center;
        background-color: rgba(99, 102, 241, 0.12);
        color: #a5b4fc;
        border: 1px solid rgba(99, 102, 241, 0.25);
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.75rem;
        margin-right: 0.5rem;
        margin-bottom: 0.5rem;
        font-family: 'Inter', sans-serif;
        font-weight: 500;
    }
    
    .source-chip svg {
        margin-right: 0.3rem;
    }
    
    /* Document list item styling */
    .doc-list-item {
        background-color: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.05);
        padding: 0.5rem 0.75rem;
        border-radius: 8px;
        margin-bottom: 0.5rem;
        font-size: 0.85rem;
        color: #d1d5db;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    
    .doc-list-item-name {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 80%;
    }
    
    /* Chat history area scroll behavior */
    .chat-history-container {
        padding-bottom: 120px;
    }

    /* Customize buttons */
    div.stButton > button {
        background-color: #1e1b4b !important;
        color: #e0e7ff !important;
        border: 1px solid #4338ca !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        transition: all 0.3s ease !important;
        width: 100%;
    }
    
    div.stButton > button:hover {
        background-color: #312e81 !important;
        border-color: #6366f1 !important;
        box-shadow: 0 0 10px rgba(99, 102, 241, 0.4) !important;
    }

    /* Special highlight for Sync button */
    .sync-btn div.stButton > button {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
        border: none !important;
        color: white !important;
    }
    
    .sync-btn div.stButton > button:hover {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
        box-shadow: 0 0 15px rgba(124, 58, 237, 0.5) !important;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to clear session state history
def clear_chat_history():
    st.session_state.messages = []
    st.session_state.suggested_questions = True
    logger.info("Chat history cleared.")

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state.messages = []
    
if "vector_store" not in st.session_state:
    with st.spinner("Initializing Vector Database & Models..."):
        st.session_state.vector_store = StartupTNVectorStore()
        # Initial sync
        st.session_state.vector_store.sync_database()
        
if "rag_pipeline" not in st.session_state:
    st.session_state.rag_pipeline = GeminiRAGPipeline(st.session_state.vector_store.get_retriever())

# Get references to instances
vector_store = st.session_state.vector_store
rag_pipeline = st.session_state.rag_pipeline

# SIDEBAR IMPLEMENTATION
with st.sidebar:
    st.markdown('<div class="brand-title">StartupTN</div>', unsafe_allow_html=True)
    st.markdown('<div class="brand-subtitle">AI Assistant & Knowledge Hub</div>', unsafe_allow_html=True)
    
    # Database statistics
    st.markdown('<div class="sidebar-section-title">Knowledge Base Status</div>', unsafe_allow_html=True)
    
    doc_count = vector_store.get_document_count()
    indexed_files = vector_store.get_indexed_files()
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Files Indexed", value=len(indexed_files))
    with col2:
        st.metric(label="Text Chunks", value=doc_count)
        
    # Document list inside sidebar
    if indexed_files:
        st.markdown('<div class="sidebar-section-title">Indexed Documents</div>', unsafe_allow_html=True)
        for doc_name in indexed_files:
            st.markdown(f"""
            <div class="doc-list-item">
                <span class="doc-list-item-name" title="{doc_name}">📄 {doc_name}</span>
                <span style="color: #10b981; font-size: 0.75rem;">Active</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No documents indexed. Please add PDF files inside the `data/` folder and trigger sync.")
        
    # Synchronization Button
    st.markdown('<div class="sidebar-section-title">Actions</div>', unsafe_allow_html=True)
    st.markdown('<div class="sync-btn">', unsafe_allow_html=True)
    if st.button("🔄 Sync Local PDFs"):
        with st.spinner("Scanning data/ folder and updating index..."):
            sync_stats = vector_store.sync_database()
            time.sleep(1) # Visual padding
            
            # Show toast/message with stats
            if "status" in sync_stats and sync_stats["status"] == "error":
                st.sidebar.error(sync_stats["message"])
            else:
                indexed = sync_stats.get("indexed", [])
                deleted = sync_stats.get("deleted", [])
                added_chunks = sync_stats.get("total_chunks_added", 0)
                
                if indexed or deleted:
                    st.sidebar.success(f"Sync complete! Indexed: {len(indexed)}, Removed: {len(deleted)}, Added Chunks: {added_chunks}")
                    st.rerun()
                else:
                    st.sidebar.info("Database is already in sync with local data/ folder.")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Clear Chat Button
    if st.button("🗑️ Clear Conversation History"):
        clear_chat_history()
        st.toast("Chat history cleared!", icon="🗑️")
        st.rerun()
        
    # About Section
    st.markdown('<div class="sidebar-section-title">About</div>', unsafe_allow_html=True)
    st.caption("This chatbot uses a local vector index constructed with Sentence Transformers (all-MiniLM-L6-v2) and ChromaDB, connected to Google's Gemini LLM to answer questions specifically about StartupTN initiatives, MSME/Startup schemes, and DPIIT benefits.")

# MAIN DISPLAY AREA
st.markdown("<h1>StartupTN AI Assistant</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #9ca3af; margin-top: -0.75rem; margin-bottom: 2rem;'>Interact with our StartupTN knowledge base. Type questions below about MSME schemes, DPIIT benefits, and StartupTN hubs.</p>", unsafe_allow_html=True)

# Default suggestions if conversation is empty
if len(st.session_state.messages) == 0:
    st.markdown("### Suggested Questions")
    
    # Display suggested questions in grid layout
    col_a, col_b = st.columns(2)
    suggestions = [
        "What are the benefits of getting DPIIT registration?",
        "What schemes are available for MSMEs and Startups?",
        "Tell me about the StartupTN Coimbatore Regional Hub.",
        "What are the key initiatives of StartupTN for 2024?"
    ]
    
    with col_a:
        if st.button(f"💡 {suggestions[0]}", key="sug_1"):
            st.session_state.messages.append({"role": "user", "content": suggestions[0]})
            st.rerun()
        if st.button(f"💡 {suggestions[1]}", key="sug_2"):
            st.session_state.messages.append({"role": "user", "content": suggestions[1]})
            st.rerun()
            
    with col_b:
        if st.button(f"💡 {suggestions[2]}", key="sug_3"):
            st.session_state.messages.append({"role": "user", "content": suggestions[2]})
            st.rerun()
        if st.button(f"💡 {suggestions[3]}", key="sug_4"):
            st.session_state.messages.append({"role": "user", "content": suggestions[3]})
            st.rerun()

# Display conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        
        # Render source citations if available for assistant replies
        if msg.get("role") == "assistant" and msg.get("sources"):
            st.markdown('<div class="source-container">', unsafe_allow_html=True)
            for src in msg["sources"]:
                st.markdown(f'<span class="source-chip">📄 {src}</span>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

# Chat input at bottom
if prompt := st.chat_input("Ask a question about StartupTN..."):
    # Append user question to history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Rerun to render user message before calling pipeline
    st.rerun()

# Handle new user query execution (the latest message in state is a User message)
if len(st.session_state.messages) > 0 and st.session_state.messages[-1]["role"] == "user":
    user_query = st.session_state.messages[-1]["content"]
    
    with st.chat_message("assistant"):
        # Render loading spinner
        with st.spinner("Generating response from StartupTN database..."):
            try:
                # Execute RAG query
                answer, sources = rag_pipeline.run_query(user_query)
                
                # Append assistant reply to session state
                assistant_msg = {
                    "role": "assistant",
                    "content": answer,
                    "sources": sources
                }
                st.session_state.messages.append(assistant_msg)
                
                # Write to screen
                st.write(answer)
                
                # Display sources
                if sources:
                    st.markdown('<div class="source-container">', unsafe_allow_html=True)
                    for src in sources:
                        st.markdown(f'<span class="source-chip">📄 {src}</span>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
            except Exception as e:
                logger.error(f"Error handling user request: {str(e)}")
                err_msg = f"An unexpected error occurred: {str(e)}"
                st.error(err_msg)
                st.session_state.messages.append({"role": "assistant", "content": err_msg})
