from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os
import uuid
import logging
import re
from datetime import datetime
from document_processor import document_processor, DocumentChunk
from gemini_llm import gemini_llm
from qdrant_wrapper import qdrant_client
from typing import List, Dict, Optional
import json

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
    session_id: Optional[str] = None

# In-memory chat storage (in production, use Redis or database)
chat_sessions: Dict[str, Dict] = {}

class DocumentUploadResponse(BaseModel):
    filename: str
    chunks_created: int
    total_tokens: int
    chunks: List[DocumentChunk]

class DocumentListResponse(BaseModel):
    documents: List[dict]
    total_documents: int

def create_chat_session(session_id: str) -> Dict:
    """Create a new chat session"""
    chat_sessions[session_id] = {
        "messages": [],
        "context": [],
        "sources": [],
        "created_at": datetime.now().isoformat()
    }
    return chat_sessions[session_id]

def get_chat_session(session_id: str) -> Optional[Dict]:
    """Get existing chat session"""
    return chat_sessions.get(session_id)

def add_message_to_session(session_id: str, role: str, content: str, sources: List[str] = None):
    """Add a message to chat session"""
    if session_id not in chat_sessions:
        create_chat_session(session_id)
    
    message = {
        "role": role,  # "user" or "assistant"
        "content": content,
        "sources": sources or [],
        "timestamp": datetime.now().isoformat()
    }
    
    chat_sessions[session_id]["messages"].append(message)
    
    # Keep only last 10 messages to prevent memory overflow
    if len(chat_sessions[session_id]["messages"]) > 10:
        chat_sessions[session_id]["messages"] = chat_sessions[session_id]["messages"][-10:]

def classify_user_intent(query: str) -> Dict[str, any]:
    """Classify user intent based on the Cleen prompt taxonomy"""
    
    # Define intent patterns for each segment
    intent_patterns = {
        "acne_prone_consumers": {
            "keywords": ["teen", "teenage", "young", "hormonal", "breakout", "pimple", "blackhead", "oily skin", "mild acne"],
            "emotional": ["safe", "gentle", "simple", "easy", "confidence", "worried", "frustrated"],
            "social": ["dermatologist", "recommend", "reviews", "people", "most", "usually"],
            "situational": ["fast", "quick", "overnight", "tomorrow", "event", "sudden"],
            "risk": ["sensitive", "side effects", "damage", "irritate", "tested", "non-comedogenic"]
        },
        "science_first_enthusiasts": {
            "keywords": ["research", "study", "clinical", "evidence", "scientifically", "formulation", "ingredients", "percentage"],
            "cognitive": ["proven", "data", "literature", "peer-reviewed", "clinical trial", "efficacy"],
            "functional": ["concentration", "pH", "interaction", "balance", "unclogging", "barrier function"]
        },
        "busy_professionals": {
            "keywords": ["busy", "quick", "simple", "minimal", "multitasking", "stress", "professional", "routine"],
            "functional": ["easy", "manage", "minimal products", "time", "efficient"],
            "emotional": ["confident", "meetings", "lifestyle", "maintain"]
        },
        "mens_skincare_beginners": {
            "keywords": ["men", "male", "shaving", "razor", "bumps", "grooming", "simple", "beginner"],
            "functional": ["easiest", "minimal", "simple", "shaving", "workout", "sweat"],
            "emotional": ["confident", "clean", "complicated", "easy"]
        },
        "post_acne_healers": {
            "keywords": ["scar", "mark", "hyperpigmentation", "heal", "repair", "recovery", "fade", "texture"],
            "emotional": ["confidence", "restore", "gentle", "sensitive"],
            "functional": ["repair", "prevent", "heal", "brighten", "collagen"]
        }
    }
    
    # Define intent categories
    intent_categories = {
        "functional": ["effective", "works", "quality", "performance", "price", "routine", "ingredients"],
        "emotional": ["safe", "gentle", "confidence", "peace of mind", "trust", "easy", "simple"],
        "social": ["dermatologist", "recommend", "reviews", "people", "experts", "trending"],
        "situational": ["fast", "quick", "urgent", "tomorrow", "event", "travel", "seasonal"],
        "risk_mitigation": ["sensitive", "side effects", "safe", "tested", "gentle", "pregnancy"],
        "cognitive": ["research", "study", "evidence", "proven", "scientific", "clinical", "data"]
    }
    
    query_lower = query.lower()
    
    # Score each segment
    segment_scores = {}
    for segment, patterns in intent_patterns.items():
        score = 0
        for category, keywords in patterns.items():
            for keyword in keywords:
                if keyword in query_lower:
                    score += 1
        segment_scores[segment] = score
    
    # Find primary segment
    primary_segment = max(segment_scores, key=segment_scores.get) if segment_scores else "general"
    
    # Score intent categories
    category_scores = {}
    for category, keywords in intent_categories.items():
        score = sum(1 for keyword in keywords if keyword in query_lower)
        category_scores[category] = score
    
    # Find primary intent category
    primary_category = max(category_scores, key=category_scores.get) if category_scores else "functional"
    
    return {
        "primary_segment": primary_segment,
        "primary_intent_category": primary_category,
        "segment_scores": segment_scores,
        "category_scores": category_scores,
        "confidence": max(segment_scores.values()) / len(query.split()) if query.split() else 0
    }

def should_fetch_documents(query: str, session: Dict) -> bool:
    """Determine if we should fetch new documents or use chat context"""
    # Always fetch for first message
    if not session["messages"]:
        return True
    
    # Check if query seems like a follow-up question
    follow_up_indicators = [
        "what about", "tell me more", "explain", "how about", "also", "additionally",
        "can you", "could you", "please", "?", "more", "further", "elaborate"
    ]
    
    query_lower = query.lower()
    is_follow_up = any(indicator in query_lower for indicator in follow_up_indicators)
    
    # If it's a follow-up and we have recent context, use chat memory
    if is_follow_up and len(session["messages"]) >= 2:
        return False
    
    # For new topics or specific questions, fetch documents
    return True

def extract_url_from_content(content: str) -> str:
    """Extract clean URL from document content"""
    
    # Look for PMID: pattern first and construct PubMed URL
    pmid_match = re.search(r'PMID:\s*(\d+)', content, re.IGNORECASE)
    if pmid_match:
        pmid = pmid_match.group(1)
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    
    # Look for DOI pattern
    doi_match = re.search(r'doi:\s*([^\s\n]+)', content, re.IGNORECASE)
    if doi_match:
        doi = doi_match.group(1).strip()
        if not doi.startswith('http'):
            return f"https://doi.org/{doi}"
        return doi
    
    # Look for clean URL patterns first (most restrictive)
    clean_url_patterns = [
        r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s\n]*)?',  # Clean URLs
        r'https?://pubmed\.ncbi\.nlm\.nih\.gov/\d+/',  # PubMed URLs
        r'https?://doi\.org/[^\s\n,;.!?()]+',  # DOI URLs (more complete)
        r'https?://dermnetnz\.org/[^\s\n,;.!?()]*',  # DermNet URLs (more complete)
        r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/[^\s\n,;.!?()]*',  # General URLs with paths
    ]
    
    for pattern in clean_url_patterns:
        match = re.search(pattern, content)
        if match:
            url = match.group(0).strip()
            # Clean up any trailing punctuation
            url = re.sub(r'[.,;!?]+$', '', url)
            return url
    
    # Look for URL: pattern with better cleaning
    url_match = re.search(r'URL:\s*(https?://[^\s\n]+)', content, re.IGNORECASE)
    if url_match:
        url = url_match.group(1).strip()
        # Clean up any trailing punctuation
        url = re.sub(r'[.,;!?]+$', '', url)
        return url
    
    # Look for any other clean URL patterns
    fallback_patterns = [
        r'https?://[^\s\n,;.!?()]+',  # URLs without common separators
    ]
    
    for pattern in fallback_patterns:
        match = re.search(pattern, content)
        if match:
            url = match.group(0).strip()
            # Clean up any trailing punctuation
            url = re.sub(r'[.,;!?]+$', '', url)
            return url
    
    return None

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
    """Query documents using hybrid search + Gemini LLM with chat memory"""
    query_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    
    # Generate session ID if not provided
    session_id = request.session_id or str(uuid.uuid4())
    
    logger.info(f"🔍 [QUERY-{query_id}] Starting query: '{request.query}' (Session: {session_id[:8]})")
    
    try:
        # Get or create chat session
        session = get_chat_session(session_id)
        if not session:
            session = create_chat_session(session_id)
            logger.info(f"🔍 [QUERY-{query_id}] Created new chat session: {session_id[:8]}")
        else:
            logger.info(f"🔍 [QUERY-{query_id}] Using existing chat session: {session_id[:8]} ({len(session['messages'])} messages)")
        
        # Add user message to session
        add_message_to_session(session_id, "user", request.query)
        
        # Classify user intent
        intent_analysis = classify_user_intent(request.query)
        logger.info(f"🔍 [QUERY-{query_id}] Intent Analysis: {intent_analysis['primary_segment']} - {intent_analysis['primary_intent_category']} (confidence: {intent_analysis['confidence']:.2f})")
        
        # Determine if we should fetch documents or use chat context
        should_fetch = should_fetch_documents(request.query, session)
        logger.info(f"🔍 [QUERY-{query_id}] Should fetch documents: {should_fetch}")
        
        if should_fetch:
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
                sources = []
                
                logger.info(f"🔍 [QUERY-{query_id}] Total context length: {sum(len(chunk) for chunk in context_chunks)} characters")
            
                # Generate segment-specific answer using Gemini with document context
                logger.info(f"🔍 [QUERY-{query_id}] Generating segment-specific answer with Gemini LLM...")
                
                # Create segment-specific prompt
                segment = intent_analysis["primary_segment"]
                intent_category = intent_analysis["primary_intent_category"]
                
                segment_prompts = {
                    "acne_prone_consumers": "Focus on safe, gentle, simple solutions suitable for teens and young adults. Emphasize non-irritating ingredients and easy-to-follow routines.",
                    "science_first_enthusiasts": "Provide detailed scientific information, research data, and evidence-based recommendations. Include specific studies, percentages, and clinical data.",
                    "busy_professionals": "Give practical, time-efficient solutions. Focus on minimal steps, multitasking products, and routines that fit busy schedules.",
                    "mens_skincare_beginners": "Provide straightforward, no-nonsense advice. Focus on simple routines, easy-to-use products, and practical solutions.",
                    "post_acne_healers": "Focus on gentle healing, scar reduction, and prevention. Emphasize safe ingredients and gradual improvement."
                }
                
                intent_guidance = {
                    "functional": "Focus on effectiveness, performance, and practical results.",
                    "emotional": "Emphasize safety, gentleness, and peace of mind.",
                    "social": "Include expert recommendations and peer validation.",
                    "situational": "Address urgency and convenience factors.",
                    "risk_mitigation": "Highlight safety, testing, and side effect considerations.",
                    "cognitive": "Provide research, data, and scientific evidence."
                }
                
                segment_guidance = segment_prompts.get(segment, "")
                intent_guidance_text = intent_guidance.get(intent_category, "")
                
                enhanced_prompt = f"""
You are a skincare expert responding to a {segment.replace('_', ' ')} user with {intent_category} intent.

User Question: {request.query}

Guidance for this user type: {segment_guidance}
Intent guidance: {intent_guidance_text}

Based on the document context below, provide a helpful, personalized answer that addresses their specific needs and concerns.

Document Context:
{chr(10).join(context_chunks)}

Answer:"""
                
                answer = gemini_llm.generate_answer(enhanced_prompt, [])
                logger.info(f"🔍 [QUERY-{query_id}] Segment-specific answer generated: {len(answer)} characters")
                
                # Extract URLs using fast regex from search results only
                if len(session["messages"]) <= 2:  # Only extract URLs for first question
                    logger.info(f"🔍 [QUERY-{query_id}] Using fast regex to extract URLs from {len(search_results)} search results...")
                    
                    sources = []
                    for result in search_results:
                        url = extract_url_from_content(result["content"])
                        if url:
                            sources.append(url)
                            logger.info(f"🔍 [QUERY-{query_id}] Extracted URL from {result['filename']}: {url}")
                        else:
                            sources.append(result["filename"])
                            logger.info(f"🔍 [QUERY-{query_id}] No URL found in {result['filename']}, using filename")
                    
                    logger.info(f"🔍 [QUERY-{query_id}] Fast regex extraction completed: {len(sources)} URLs extracted")
                else:
                    # Use cached sources from previous questions for follow-ups
                    sources = session.get("sources", [])
                    logger.info(f"🔍 [QUERY-{query_id}] Using cached sources for follow-up question: {len(sources)} URLs")
                
                # Update session context with extracted sources
                session["context"] = context_chunks
                session["sources"] = list(set(sources))
                logger.info(f"🔍 [QUERY-{query_id}] Final sources: {list(set(sources))}")
                
                # Add assistant response to session
                add_message_to_session(session_id, "assistant", answer, list(set(sources)))
            
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                logger.info(f"🔍 [QUERY-{query_id}] Query complete in {duration:.2f}s")
                
                return {
                    "answer": answer,
                    "sources": list(set(sources)),  # Remove duplicates
                    "search_results": search_results,
                    "session_id": session_id,
                    "used_documents": True,
                    "intent_analysis": intent_analysis
                }
            else:
                # No documents found, use Gemini without context
                logger.info(f"🔍 [QUERY-{query_id}] No relevant documents found, using general knowledge")
                answer = gemini_llm.generate_answer(request.query)
                logger.info(f"🔍 [QUERY-{query_id}] General answer generated: {len(answer)} characters")
                
                # Add assistant response to session
                add_message_to_session(session_id, "assistant", answer, ["No relevant documents found"])
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                logger.info(f"🔍 [QUERY-{query_id}] Query complete in {duration:.2f}s")
                
                return {
                    "answer": answer,
                    "sources": ["No relevant documents found - using general knowledge"],
                    "search_results": [],
                    "session_id": session_id,
                    "used_documents": False,
                    "intent_analysis": intent_analysis
                }
        else:
            # Use chat context instead of fetching documents
            logger.info(f"🔍 [QUERY-{query_id}] Using chat context instead of fetching documents")
            
            # Build context from previous messages
            chat_context = []
            for msg in session["messages"][-4:]:  # Last 4 messages
                if msg["role"] == "assistant":
                    chat_context.append(f"Previous answer: {msg['content']}")
            
            # Add current context if available
            if session["context"]:
                chat_context.extend(session["context"])
            
            logger.info(f"🔍 [QUERY-{query_id}] Using chat context: {len(chat_context)} context pieces")
            
            # Generate answer using chat context
            answer = gemini_llm.generate_answer(request.query, chat_context)
            logger.info(f"🔍 [QUERY-{query_id}] Answer generated from chat context: {len(answer)} characters")
            
            # Add assistant response to session
            add_message_to_session(session_id, "assistant", answer, session.get("sources", []))
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"🔍 [QUERY-{query_id}] Query complete in {duration:.2f}s")
            
            return {
                "answer": answer,
                "sources": session.get("sources", []),
                "search_results": [],
                "session_id": session_id,
                "used_documents": False,
                "used_chat_context": True,
                "intent_analysis": intent_analysis
            }
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.error(f"🔍 [QUERY-{query_id}] ❌ Query failed after {duration:.2f}s: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)