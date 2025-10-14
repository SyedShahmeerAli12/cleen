from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os
import uuid
import logging
from datetime import datetime
from document_processor import document_processor, DocumentChunk
from gemini_llm import gemini_llm
from qdrant_wrapper import qdrant_client
from typing import List

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/app/logs/rag_system.log')
    ]
)
logger = logging.getLogger(__name__)

# Create logs directory
os.makedirs('/app/logs', exist_ok=True)

app = FastAPI(title="Personal RAG API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@postgres:5432/personal_rag")
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")

class QueryRequest(BaseModel):
    query: str

class DocumentUploadResponse(BaseModel):
    filename: str
    chunks_created: int
    total_tokens: int
    chunks: List[DocumentChunk]

class DocumentListResponse(BaseModel):
    documents: List[dict]
    total_documents: int

@app.get("/")
async def root():
    return {"message": "Personal RAG API is running!", "status": "healthy"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check Qdrant connection using our client
        qdrant_status = await qdrant_client.is_ready()
    except:
        qdrant_status = False
    
    return {
        "status": "healthy",
        "qdrant_connected": qdrant_status,
        "database_url": DATABASE_URL
    }

# --------- Backend Startup (no document processing) ---------
@app.on_event("startup")
async def backend_startup() -> None:
    """Backend startup - document processing handled by separate indexer service"""
    logger.info("🚀 Backend starting up...")
    logger.info("📊 Document indexing handled by separate indexer service")
    
    # Check Qdrant connection
    try:
        count = qdrant_client.get_point_count()
        logger.info(f"📊 Current vector count: {count}")
        logger.info("💡 Backend ready for queries!")
    except Exception as e:
        logger.error(f"❌ Backend startup error: {e}")

# Endpoint to ingest any new files later, without deleting existing
@app.post("/ingest-new")
async def ingest_new_documents():
    try:
        docs_dir = os.path.join(os.getcwd(), "data", "documents")
        if not os.path.isdir(docs_dir):
            return {"status": "no_dir", "message": f"No documents directory at {docs_dir}"}

        supported_exts = {".pdf", ".docx", ".txt", ".md", ".json", ".csv"}
        added = 0
        for root_dir, _, files in os.walk(docs_dir):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in supported_exts:
                    continue
                path = os.path.join(root_dir, fname)
                try:
                    with open(path, "rb") as f:
                        content = f.read()
                    chunks = document_processor.process_document(content, fname)
                    for i, chunk in enumerate(chunks):
                        deterministic_id = f"{fname}_{i}"
                        await qdrant_client.store_document(chunk, deterministic_id)
                        added += 1
                except Exception as e:
                    print(f"Ingest-new error for {fname}: {e}")
        return {"status": "ok", "chunks_added": added}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """Upload and process a document with detailed logging"""
    upload_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    
    logger.info(f"📤 [UPLOAD-{upload_id}] Starting document upload: {file.filename}")
    logger.info(f"📤 [UPLOAD-{upload_id}] File size: {file.size if hasattr(file, 'size') else 'Unknown'} bytes")
    
    try:
        # Read file content
        logger.info(f"📤 [UPLOAD-{upload_id}] Reading file content...")
        file_content = await file.read()
        logger.info(f"📤 [UPLOAD-{upload_id}] File content read: {len(file_content)} bytes")
        
        # Process document using Onyx's method
        logger.info(f"📤 [UPLOAD-{upload_id}] Starting document processing...")
        chunks = document_processor.process_document(file_content, file.filename)
        logger.info(f"📤 [UPLOAD-{upload_id}] Document processed: {len(chunks)} chunks created")
        
        # Calculate stats
        total_tokens = sum(chunk.token_count for chunk in chunks)
        logger.info(f"📤 [UPLOAD-{upload_id}] Total tokens across all chunks: {total_tokens}")
        
        # Store chunks in Qdrant
        logger.info(f"📤 [UPLOAD-{upload_id}] Starting chunk storage in Qdrant...")
        stored_count = 0
        for i, chunk in enumerate(chunks):
            doc_id = f"{file.filename}_{i}_{uuid.uuid4().hex[:8]}"
            logger.info(f"📤 [UPLOAD-{upload_id}] Storing chunk {i+1}/{len(chunks)}: {doc_id}")
            logger.info(f"📤 [UPLOAD-{upload_id}] Chunk {i+1} content preview: {chunk.content[:100]}...")
            logger.info(f"📤 [UPLOAD-{upload_id}] Chunk {i+1} token count: {chunk.token_count}")
            
            success = await qdrant_client.store_document(chunk, doc_id)
            if success:
                stored_count += 1
                logger.info(f"📤 [UPLOAD-{upload_id}] ✅ Chunk {i+1} stored successfully")
            else:
                logger.error(f"📤 [UPLOAD-{upload_id}] ❌ Failed to store chunk {i+1}")
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"📤 [UPLOAD-{upload_id}] Upload complete!")
        logger.info(f"📤 [UPLOAD-{upload_id}] Summary: {stored_count}/{len(chunks)} chunks stored")
        logger.info(f"📤 [UPLOAD-{upload_id}] Total processing time: {duration:.2f} seconds")
        
        return DocumentUploadResponse(
            filename=file.filename,
            chunks_created=len(chunks),
            total_tokens=total_tokens,
            chunks=chunks
        )
    
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.error(f"📤 [UPLOAD-{upload_id}] ❌ Upload failed after {duration:.2f}s: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")

@app.get("/documents", response_model=DocumentListResponse)
async def list_documents():
    """List processed documents"""
    # Placeholder - will implement proper storage in Phase 3
    return DocumentListResponse(
        documents=[],
        total_documents=0
    )

@app.post("/query")
async def query_documents(request: QueryRequest):
    """Query documents using hybrid search + Gemini LLM with detailed logging"""
    query_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    
    logger.info(f"🔍 [QUERY-{query_id}] Starting query: '{request.query}'")
    
    try:
        # Generate query embedding
        logger.info(f"🔍 [QUERY-{query_id}] Generating query embedding...")
        query_embedding = document_processor.generate_query_embedding(request.query)
        logger.info(f"🔍 [QUERY-{query_id}] Query embedding generated: {len(query_embedding)} dimensions")
        
        # Perform hybrid search in Qdrant
        logger.info(f"🔍 [QUERY-{query_id}] Performing hybrid search in Qdrant...")
        search_results = await qdrant_client.hybrid_search(
            query=request.query,
            query_embedding=query_embedding,
            limit=5
        )
        logger.info(f"🔍 [QUERY-{query_id}] Search completed: {len(search_results)} results found")
        
        if search_results:
            # Extract content from search results
            context_chunks = [result["content"] for result in search_results]
            sources = [result["filename"] for result in search_results]
            
            logger.info(f"🔍 [QUERY-{query_id}] Context sources: {list(set(sources))}")
            logger.info(f"🔍 [QUERY-{query_id}] Total context length: {sum(len(chunk) for chunk in context_chunks)} characters")
            
            # Generate answer using Gemini with document context
            logger.info(f"🔍 [QUERY-{query_id}] Generating answer with Gemini LLM...")
            answer = gemini_llm.generate_answer(request.query, context_chunks)
            logger.info(f"🔍 [QUERY-{query_id}] Answer generated: {len(answer)} characters")
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"🔍 [QUERY-{query_id}] Query complete in {duration:.2f}s")
            
            return {
                "answer": answer,
                "sources": list(set(sources)),  # Remove duplicates
                "search_results": search_results
            }
        else:
            # No documents found, use Gemini without context
            logger.info(f"🔍 [QUERY-{query_id}] No relevant documents found, using general knowledge")
            answer = gemini_llm.generate_answer(request.query)
            logger.info(f"🔍 [QUERY-{query_id}] General answer generated: {len(answer)} characters")
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"🔍 [QUERY-{query_id}] Query complete in {duration:.2f}s")
            
            return {
                "answer": answer,
                "sources": ["No relevant documents found - using general knowledge"],
                "search_results": []
            }
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.error(f"🔍 [QUERY-{query_id}] ❌ Query failed after {duration:.2f}s: {str(e)}")
        return {
            "answer": f"Error: {str(e)}",
            "sources": ["Error occurred"],
            "search_results": []
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)