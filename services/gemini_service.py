import os
import logging
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv
import google.generativeai as genai
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# Load local environment variables
load_dotenv()

# Check and configure Gemini API Key
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    # Try reading the key directly from the .env file in the workspace
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            content = f.read().strip()
            # If the file contains only the raw key, set it
            if "=" not in content and len(content) > 20:
                api_key = content
                os.environ["GEMINI_API_KEY"] = api_key
            else:
                # Standard parsing of .env
                for line in content.split("\n"):
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        os.environ["GEMINI_API_KEY"] = api_key
                        break

if api_key:
    genai.configure(api_key=api_key)
    logger.info("Gemini API configured successfully.")
else:
    logger.warning("GEMINI_API_KEY not found in env variables or .env file.")

# Define prompt template
PROMPT_TEMPLATE = """You are StartupTN AI Assistant, an intelligent AI advisor built exclusively for Startup Tamil Nadu.
Your purpose is to provide clear, professional, easy-to-understand, and trustworthy answers about StartupTN, government startup schemes, funding, incubators, DPIIT, MSME schemes, registration, and entrepreneurship.

Answer the user's question based strictly on the provided context below.

Context:
{context}

Question: {question}

=========================
PRIMARY RULES
=========================
1. Answer ONLY using the provided context.
2. Never make up facts.
3. If the answer cannot be found in the context, politely reply exactly:
"I couldn't find sufficient information in the StartupTN knowledge base to answer this question."
Then suggest 2-3 related questions about StartupTN schemes or DPIIT benefits if possible.
4. Do NOT mention "Based on the provided context..." or "According to the context...".
5. Never expose internal implementation details like embeddings, vector database, chunks, retrieval, or RAG.
6. Write as if you are an official StartupTN support assistant.

=========================
RESPONSE STYLE
=========================
Structure your response exactly as follows whenever applicable (do not include headers that are not applicable to the question):

# Short Answer
A 2-3 sentence summary that directly answers the user's question.

# Detailed Explanation
Explain the topic in simple English. Avoid copying sentences directly from the context. Rewrite naturally, as if explaining to a startup founder.

# Benefits
Use bullet points if applicable.

# Eligibility
Explain who can apply if applicable.

# Process / Steps
Write numbered steps if applicable.

# Important Notes
Mention any conditions, limitations, or exceptions.

# Related StartupTN Schemes
If relevant, recommend other schemes.

=========================
WRITING STYLE
=========================
- Use professional, warm English.
- Avoid robotic wording.
- Avoid repeating information.
- Use headings, bullet points, and numbered lists.
- Explain abbreviations when first introduced.
- Keep paragraphs short.
- Never dump raw text. Rewrite everything naturally.

Answer:"""

class GeminiRAGPipeline:
    """
    Builds and manages a Retrieval-Augmented Generation (RAG) pipeline using LangChain
    and Google Gemini API.
    """
    def __init__(self, retriever: Any):
        self.retriever = retriever
        self.fallback_message = (
            "I couldn't find sufficient information in the StartupTN knowledge base to answer this question.\n\n"
            "**Here are some related questions you can ask:**\n"
            "- What are the benefits of getting DPIIT registration?\n"
            "- What schemes are available for MSMEs and Startups?\n"
            "- Tell me about the StartupTN Coimbatore Regional Hub."
        )
        
        # Initialize Gemini model
        # Use gemini-3.5-flash as the standard model in this environment
        self.model = genai.GenerativeModel("gemini-3.5-flash")
        
        # Build LangChain RAG pipeline
        self._build_chain()

    def _build_chain(self):
        # LangChain Runnable for retrieving documents
        retrieve_docs = RunnableLambda(lambda inputs: self.retriever.invoke(inputs["question"]))
        
        # LangChain Runnable to format documents into a single context string
        format_docs = RunnableLambda(lambda docs: self._format_context(docs))
        
        # LangChain Runnable to call Gemini API
        generate_response = RunnableLambda(lambda inputs: self._generate_gemini_response(inputs["context"], inputs["question"]))
        
        # Combine the steps into a RAG chain
        self.chain = (
            {
                "context": retrieve_docs | format_docs,
                "question": lambda x: x["question"],
                "raw_docs": retrieve_docs
            }
            | RunnablePassthrough.assign(
                answer=generate_response
            )
        )

    def _format_context(self, docs: List[Document]) -> str:
        """
        Combines list of documents into a single formatted context string.
        """
        if not docs:
            return ""
        formatted_chunks = []
        for i, doc in enumerate(docs):
            source = doc.metadata.get("source", "Unknown Document")
            page = doc.metadata.get("page", "N/A")
            formatted_chunks.append(f"[Chunk {i+1} | Source: {source} (Page {page})]\n{doc.page_content}")
        return "\n\n".join(formatted_chunks)

    def _generate_gemini_response(self, context: str, question: str) -> str:
        """
        Sends context and question to Gemini and generates a response.
        """
        # If context is empty, return the fallback message immediately without calling Gemini
        if not context or context.strip() == "":
            return self.fallback_message
            
        try:
            prompt = PROMPT_TEMPLATE.format(context=context, question=question)
            
            # Request Gemini generation with low temperature for factual RAG consistency
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                )
            )
            
            answer = response.text.strip()
            
            # Post-process response to ensure compliance with fallback instructions
            answer_lower = answer.lower()
            if not answer or "couldn't find" in answer_lower or "not mention" in answer_lower or "no information" in answer_lower or "sufficient information" in answer_lower:
                # If model is saying it cannot find the info, normalize to the requested response
                if not any(k in answer for k in ["StartupTN knowledge base", "I couldn't find"]):
                    return self.fallback_message
                    
            return answer
        except Exception as e:
            logger.error(f"Error calling Gemini API: {str(e)}")
            return f"An error occurred while generating response: {str(e)}"

    def run_query(self, question: str) -> Tuple[str, List[str]]:
        """
        Runs a user query through the RAG pipeline.
        
        Returns:
            Tuple[str, List[str]]: (Generated Answer, List of unique source document names)
        """
        if not api_key:
            return "Error: Gemini API key is missing or not configured. Please check your .env file.", []
            
        try:
            logger.info(f"Running query: {question}")
            output = self.chain.invoke({"question": question})
            
            answer = output["answer"]
            raw_docs = output["raw_docs"]
            
            # Extract unique source names
            sources = []
            if answer != self.fallback_message:
                unique_sources = set()
                for doc in raw_docs:
                    source_name = doc.metadata.get("source")
                    if source_name:
                        unique_sources.add(source_name)
                sources = sorted(list(unique_sources))
                
            return answer, sources
        except Exception as e:
            logger.error(f"RAG execution failed: {str(e)}")
            return f"Failed to get a response from the model: {str(e)}", []
