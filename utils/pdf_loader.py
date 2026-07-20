import os
import logging
from pypdf import PdfReader
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

def load_pdfs_from_directory(directory_path: str) -> list[Document]:
    """
    Automatically scans the directory_path for PDF files, extracts text page-by-page
    using PyPDF, and returns a list of LangChain Document objects.
    
    Args:
        directory_path (str): The folder containing PDF documents.
        
    Returns:
        list[Document]: A list of extracted documents.
    """
    documents = []
    
    if not os.path.exists(directory_path):
        logger.error(f"Directory '{directory_path}' does not exist.")
        return documents

    pdf_files = [f for f in os.listdir(directory_path) if f.lower().endswith(".pdf")]
    
    if not pdf_files:
        logger.warning(f"No PDF files found in directory '{directory_path}'.")
        return documents
        
    logger.info(f"Found {len(pdf_files)} PDF files to process in '{directory_path}'.")
    
    for filename in pdf_files:
        file_path = os.path.join(directory_path, filename)
        logger.info(f"Processing PDF file: {filename}")
        try:
            reader = PdfReader(file_path)
            num_pages = len(reader.pages)
            for page_num in range(num_pages):
                page = reader.pages[page_num]
                text = page.extract_text() or ""
                text = text.strip()
                
                # Only keep pages with content
                if text:
                    metadata = {
                        "source": filename,
                        "page": page_num + 1,
                        "file_path": file_path
                    }
                    documents.append(Document(page_content=text, metadata=metadata))
            logger.info(f"Successfully processed {filename} ({num_pages} pages).")
        except Exception as e:
            logger.error(f"Failed to parse {filename}: {str(e)}")
            
    logger.info(f"Extracted a total of {len(documents)} pages from PDFs.")
    return documents
