import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

def split_documents(documents: list[Document], chunk_size: int = 1000, chunk_overlap: int = 200) -> list[Document]:
    """
    Splits list of LangChain Document objects into smaller, overlapping chunks.
    
    Args:
        documents (list[Document]): List of input documents.
        chunk_size (int): Max size of a chunk in characters.
        chunk_overlap (int): Number of overlapping characters between adjacent chunks.
        
    Returns:
        list[Document]: List of chunked documents.
    """
    if not documents:
        logger.warning("Empty document list passed for splitting.")
        return []
        
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False
    )
    
    chunks = text_splitter.split_documents(documents)
    logger.info(f"Split {len(documents)} documents into {len(chunks)} chunks (size={chunk_size}, overlap={chunk_overlap}).")
    return chunks
