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
    """Enhanced intent classification with client's detailed prompts and Jobs-to-Be-Done analysis"""
    
    # Enhanced intent patterns with client's specific prompts
    intent_patterns = {
        "acne_prone_consumers": {
            "functional": [
                "effective treatment", "mild hormonal acne", "doesn't dry out skin", "clear forehead", "chin breakouts", 
                "fast without irritating", "daily cleanser", "prevent new pimples", "blackheads and oily skin",
                "reduce acne", "prescription medication", "simple three-step", "acne-prone skin"
            ],
            "emotional": [
                "safest for teenage", "stop breakouts", "damaging skin barrier", "simple routine", 
                "safe ingredients", "keeps breaking out", "gentle", "confidence", "peace of mind"
            ],
            "social": [
                "dermatologists recommend", "teenage acne", "most people", "acne-prone skin", 
                "best online reviews", "peer validation", "expert recommendations"
            ],
            "situational": [
                "calm acne before event", "tomorrow", "sudden breakouts", "fast at home", 
                "overnight treatment", "reduce spots quickly", "urgent", "convenience"
            ],
            "risk_mitigation": [
                "safest for sensitive skin", "non-comedogenic", "dermatologist tested", 
                "gentle way to start", "without side effects", "safe", "tested"
            ],
            "cognitive": [
                "clinically proven", "reduce acne", "science-based routine", "control breakouts", 
                "research says", "effective ingredients", "evidence", "proven"
            ]
        },
        "science_first_enthusiasts": {
            "functional": [
                "effective formulation", "unclogging pores", "over-drying", "balance oil production", 
                "skin barrier function", "percentage of active ingredients", "comedonal acne", 
                "concentration", "pH", "interaction", "balance"
            ],
            "emotional": [
                "evidence-based skincare", "adult acne", "supported by dermatology research", 
                "measurable improvement", "within a month", "trust", "confidence"
            ],
            "social": [
                "recommended by cosmetic chemists", "dermatology experts", "adult acne naturally", 
                "scientifically proven ingredients", "trending in professional skincare", 
                "expert recommendations"
            ],
            "situational": [
                "adjust acne routine", "seasonal skin changes", "humid environments", 
                "polluted environments", "travel", "environmental factors"
            ],
            "risk_mitigation": [
                "least likely to irritate", "sensitive skin", "combined", "test new products safely", 
                "using retinoids", "safe combinations", "gentle"
            ],
            "cognitive": [
                "peer-reviewed studies", "topical treatments for acne", "highest evidence level", 
                "acne reduction", "clinically validated alternatives", "antibiotics for acne", 
                "research", "clinical trials", "scientific evidence"
            ]
        },
        "busy_professionals": {
            "functional": [
                "easiest acne routine", "busy people", "manage adult acne", "minimal products", 
                "multitasking skincare products", "prevent breakouts", "time-efficient", "simple"
            ],
            "emotional": [
                "quick routine", "confident before meetings", "maintain clear skin", 
                "high-stress lifestyle", "confidence", "peace of mind"
            ],
            "social": [
                "professionals with busy schedules", "clearer skin", "simple skincare steps", 
                "recommended by dermatologists", "adults", "peer validation"
            ],
            "situational": [
                "breakouts caused by travel", "masks", "prevent stress-related acne", 
                "without changing schedule", "urgent", "convenience"
            ],
            "risk_mitigation": [
                "dermatologist-approved treatments", "minimal side effects", "safe acne routine", 
                "during pregnancy", "while on medication", "safe", "tested"
            ],
            "cognitive": [
                "research supports", "niacinamide", "azelaic acid", "proven ingredients", 
                "adult women", "hormonal breakouts", "evidence", "scientific"
            ]
        },
        "mens_skincare_beginners": {
            "functional": [
                "simplest way to treat", "acne and razor bumps", "clear breakouts", 
                "without adding lots of products", "face wash", "prevent shaving irritation", 
                "easiest", "minimal", "simple"
            ],
            "emotional": [
                "easy routine", "look clean and confident", "take care of skin", 
                "without feeling complicated", "confidence", "simple"
            ],
            "social": [
                "skincare routine", "most men follow", "acne control", "barbers recommend", 
                "grooming experts", "clear skin", "peer validation"
            ],
            "situational": [
                "after workouts", "prevent breakouts", "acne caused by sweat", 
                "shaving", "workout", "sweat"
            ],
            "risk_mitigation": [
                "gentle options", "without causing dryness", "redness", "safe for daily shaving", 
                "routines", "safe", "gentle"
            ],
            "cognitive": [
                "dermatologist-backed steps", "reduce acne", "scientifically support", 
                "clearer skin for men", "evidence", "research"
            ]
        },
        "post_acne_healers": {
            "functional": [
                "fade dark marks", "acne scars effectively", "repair skin texture", 
                "after breakouts", "routine prevents new acne", "healing old scars", 
                "repair", "prevent", "heal", "brighten"
            ],
            "emotional": [
                "restore confidence", "after long-term acne", "gentle brightening ingredients", 
                "safe for sensitive skin", "confidence", "restore", "gentle"
            ],
            "social": [
                "dermatologists recommend", "post-acne hyperpigmentation", "routines", 
                "real people used", "heal acne scars successfully", "peer validation"
            ],
            "situational": [
                "repair skin after", "prescription acne treatments", "prevent dryness", 
                "peeling during retinoid recovery", "recovery", "healing"
            ],
            "risk_mitigation": [
                "post-acne treatments", "safe for sensitive", "reactive skin", 
                "routines prevent scarring", "after active acne clears", "safe", "gentle"
            ],
            "cognitive": [
                "proven clinical efficacy", "post-acne marks", "research says", 
                "niacinamide", "retinol", "azelaic acid", "healing skin", 
                "scientific evidence", "collagen-boosting skincare", "after acne", 
                "research", "clinical evidence"
            ]
        }
    }
    
    # Jobs-to-Be-Done patterns for each segment
    jobs_to_be_done = {
        "acne_prone_consumers": {
            "identify_acne_cause": ["cause", "type of acne", "what's causing", "why am I breaking out", "acne type"],
            "learn_effective_ingredients": ["ingredients", "most effective", "work for my skin", "what ingredients", "best ingredients"],
            "build_simple_routine": ["routine", "simple routine", "three-step", "daily routine", "skincare routine"],
            "find_affordable_products": ["affordable", "budget", "cheap", "price", "cost-effective"],
            "track_skin_progress": ["progress", "track", "improvement", "results", "before and after"]
        },
        "science_first_enthusiasts": {
            "validate_with_science": ["research", "studies", "clinical", "evidence", "peer-reviewed", "scientific"],
            "evaluate_ingredient_efficacy": ["efficacy", "effectiveness", "data", "proven", "clinical trial"],
            "compare_formulations": ["formulation", "concentration", "percentage", "compare", "different brands"],
            "understand_interactions": ["interaction", "pH", "balance", "combine", "layering"],
            "stay_updated_on_science": ["latest", "new research", "recent studies", "updated", "current"]
        },
        "busy_professionals": {
            "quick_identification": ["quick", "fast", "easy", "simple", "minimal"],
            "maintain_clear_skin": ["maintain", "keep clear", "prevent", "manage", "control"],
            "simplify_routine": ["simple", "minimal", "multitasking", "fewer products", "streamlined"],
            "save_time": ["time", "efficient", "quick", "fast", "busy"],
            "avoid_trial_error": ["proven", "tested", "reliable", "trusted", "recommended"]
        },
        "mens_skincare_beginners": {
            "understand_basics": ["basics", "beginner", "simple", "easy", "start"],
            "fix_acne_razor_bumps": ["acne", "razor bumps", "ingrown hairs", "shaving", "irritation"],
            "adopt_minimal_routine": ["minimal", "simple", "daily", "routine", "basic"],
            "buy_effective_products": ["effective", "works", "affordable", "easy to use", "simple"],
            "blend_grooming_skincare": ["grooming", "shaving", "skincare", "routine", "daily"]
        },
        "post_acne_healers": {
            "fade_scars_marks": ["fade", "scars", "dark marks", "hyperpigmentation", "spots"],
            "rebuild_skin_barrier": ["skin barrier", "repair", "strengthen", "rebuild", "restore"],
            "prevent_future_breakouts": ["prevent", "future breakouts", "new acne", "while healing"],
            "identify_safe_actives": ["safe", "retinoids", "acids", "niacinamide", "actives"],
            "evidence_based_layering": ["layering", "sequencing", "combine", "routine", "evidence"]
        }
    }
    
    query_lower = query.lower()
    
    # Score each segment with enhanced patterns
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
    intent_categories = {
        "functional": ["effective", "works", "quality", "performance", "price", "routine", "ingredients", "treatment", "prevent"],
        "emotional": ["safe", "gentle", "confidence", "peace of mind", "trust", "easy", "simple", "comfortable"],
        "social": ["dermatologist", "recommend", "reviews", "people", "experts", "trending", "most"],
        "situational": ["fast", "quick", "urgent", "tomorrow", "event", "travel", "seasonal", "before"],
        "risk_mitigation": ["sensitive", "side effects", "safe", "tested", "gentle", "pregnancy", "non-comedogenic"],
        "cognitive": ["research", "study", "evidence", "proven", "scientific", "clinical", "data", "studies"]
    }
    
    category_scores = {}
    for category, keywords in intent_categories.items():
        score = sum(1 for keyword in keywords if keyword in query_lower)
        category_scores[category] = score
    
    # Find primary intent category
    primary_category = max(category_scores, key=category_scores.get) if category_scores else "functional"
    
    # Identify Job-to-Be-Done
    job_scores = {}
    if primary_segment in jobs_to_be_done:
        for job, keywords in jobs_to_be_done[primary_segment].items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            job_scores[job] = score
    
    primary_job = max(job_scores, key=job_scores.get) if job_scores else "general_inquiry"
    
    return {
        "primary_segment": primary_segment,
        "primary_intent_category": primary_category,
        "primary_job_to_be_done": primary_job,
        "segment_scores": segment_scores,
        "category_scores": category_scores,
        "job_scores": job_scores,
        "confidence": max(segment_scores.values()) / len(query.split()) if query.split() else 0
    }

def extract_url_from_content(content: str) -> str:
    """Extract clean, complete URL from document content with improved patterns"""
    
    # Look for PMID: pattern first and construct PubMed URL
    pmid_match = re.search(r'PMID:\s*(\d+)', content, re.IGNORECASE)
    if pmid_match:
        pmid = pmid_match.group(1)
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    
    # Look for DOI pattern with complete URL construction
    doi_match = re.search(r'doi:\s*([^\s\n]+)', content, re.IGNORECASE)
    if doi_match:
        doi = doi_match.group(1).strip()
        if not doi.startswith('http'):
            return f"https://doi.org/{doi}"
        return doi
    
    # Look for complete URL patterns (more restrictive to avoid truncation)
    complete_url_patterns = [
        r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s\n,;.!?()]*)?',  # Complete URLs
        r'https?://pubmed\.ncbi\.nlm\.nih\.gov/\d+/',  # Complete PubMed URLs
        r'https?://doi\.org/[^\s\n,;.!?()]+',  # Complete DOI URLs
        r'https?://dermnetnz\.org/[^\s\n,;.!?()]*',  # Complete DermNet URLs
        r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/[^\s\n,;.!?()]*',  # URLs with paths
    ]
    
    for pattern in complete_url_patterns:
        match = re.search(pattern, content)
        if match:
            url = match.group(0).strip()
            # Clean up any trailing punctuation
            url = re.sub(r'[.,;!?]+$', '', url)
            # Ensure URL is complete (has proper domain)
            if '.' in url.split('://')[1] and len(url.split('://')[1].split('.')[0]) > 0:
                return url
    
    # Look for URL: pattern with better cleaning
    url_match = re.search(r'URL:\s*(https?://[^\s\n]+)', content, re.IGNORECASE)
    if url_match:
        url = url_match.group(1).strip()
        # Clean up any trailing punctuation
        url = re.sub(r'[.,;!?]+$', '', url)
        # Ensure URL is complete
        if '.' in url.split('://')[1] and len(url.split('://')[1].split('.')[0]) > 0:
            return url
    
    return None

def should_fetch_documents(query: str, session: Dict) -> bool:
    """Use LLM to intelligently decide whether to fetch documents or use chat context"""
    # Always fetch for first message
    if not session["messages"]:
        return True
    
    # Build context about the conversation
    conversation_context = ""
    if session["messages"]:
        recent_messages = session["messages"][-3:]  # Last 3 messages
        conversation_context = "\n".join([
            f"{msg['role']}: {msg['content'][:200]}..." 
            for msg in recent_messages
        ])
    
    # Use LLM to decide
    decision_prompt = f"""
You are a smart assistant that decides whether to fetch new documents or use existing chat context.

CONVERSATION CONTEXT:
{conversation_context}

CURRENT QUESTION:
{query}

DECISION RULES:
- Fetch documents if: asking for new research, literature, specific facts, or topics not covered in recent conversation
- Use chat context if: asking follow-up questions, clarifications, or elaborations on recent topics

Respond with only: FETCH_DOCUMENTS or USE_CHAT_CONTEXT
"""
    
    try:
        decision = gemini_llm.generate_answer(decision_prompt, [])
        decision = decision.strip().upper()
        
        logger.info(f"🤖 LLM Decision: {decision}")
        
        if "FETCH_DOCUMENTS" in decision:
            return True
        elif "USE_CHAT_CONTEXT" in decision:
            return False
        else:
            # Default to fetching documents if unclear
            logger.warning(f"Unclear LLM decision: {decision}, defaulting to fetch documents")
            return True
            
    except Exception as e:
        logger.warning(f"LLM decision failed: {e}, defaulting to fetch documents")
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
        logger.info(f"🔍 [QUERY-{query_id}] Intent Analysis: {intent_analysis['primary_segment']} - {intent_analysis['primary_intent_category']} - Job: {intent_analysis['primary_job_to_be_done']} (confidence: {intent_analysis['confidence']:.2f})")
        
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
                
                # Create enhanced segment-specific prompt with Jobs-to-Be-Done
                segment = intent_analysis["primary_segment"]
                intent_category = intent_analysis["primary_intent_category"]
                job_to_be_done = intent_analysis["primary_job_to_be_done"]
                
                # Enhanced segment-specific guidance with Jobs-to-Be-Done
                segment_job_guidance = {
                    "acne_prone_consumers": {
                        "identify_acne_cause": "Help identify the specific type and cause of acne. Explain hormonal vs bacterial vs comedonal acne. Provide clear identification criteria.",
                        "learn_effective_ingredients": "Focus on safe, gentle ingredients suitable for teens. Explain salicylic acid, benzoyl peroxide, niacinamide. Emphasize non-irritating formulations.",
                        "build_simple_routine": "Provide a simple 3-step routine: cleanse, treat, moisturize. Focus on consistency and gentle products. Avoid overwhelming with too many steps.",
                        "find_affordable_products": "Recommend budget-friendly options. Mention drugstore brands, generic alternatives, and cost-effective ingredient concentrations.",
                        "track_skin_progress": "Explain how to track improvement, what to expect timeline-wise, and when to adjust the routine."
                    },
                    "science_first_enthusiasts": {
                        "validate_with_science": "Provide detailed scientific information, research data, and evidence-based recommendations. Include specific studies, percentages, and clinical data.",
                        "evaluate_ingredient_efficacy": "Compare ingredient concentrations, formulations, and clinical trial results. Explain mechanism of action and efficacy data.",
                        "compare_formulations": "Analyze different formulations, pH levels, and ingredient interactions. Provide scientific comparisons between products.",
                        "understand_interactions": "Explain ingredient interactions, layering protocols, and pH considerations. Provide evidence-based combination strategies.",
                        "stay_updated_on_science": "Reference latest research, clinical trials, and emerging ingredients. Provide current scientific consensus."
                    },
                    "busy_professionals": {
                        "quick_identification": "Provide fast, accurate product identification with specific brand names, concentrations, and travel-friendly options. Include morning/evening timing and workday integration tips.",
                        "maintain_clear_skin": "Emphasize maintenance strategies with specific product recommendations, application techniques, and consistency tips for 12-hour workdays.",
                        "simplify_routine": "Provide minimal, effective routines with exact product names, concentrations (e.g., 2.5% benzoyl peroxide), and step-by-step instructions. Include travel-size recommendations.",
                        "save_time": "Focus on time-efficient solutions with specific timing (e.g., 2-minute morning routine), quick application techniques, and products that work during work hours. Include travel-friendly formats.",
                        "avoid_trial_error": "Provide proven, reliable recommendations with specific brand names, concentrations, and dermatologist-tested options. Include TSA-friendly travel sizes and workday application tips."
                    },
                    "mens_skincare_beginners": {
                        "understand_basics": "Provide straightforward, no-nonsense advice. Focus on simple routines, easy-to-use products, and practical solutions.",
                        "fix_acne_razor_bumps": "Address both acne and shaving-related issues. Provide solutions for ingrown hairs and razor irritation.",
                        "adopt_minimal_routine": "Suggest a simple daily routine that fits into existing habits. Focus on ease of use and consistency.",
                        "buy_effective_products": "Recommend effective, affordable products that are easy to use. Avoid complicated formulations.",
                        "blend_grooming_skincare": "Integrate skincare with grooming routines. Focus on post-shave care and workout skincare."
                    },
                    "post_acne_healers": {
                        "fade_scars_marks": "Focus on gentle healing, scar reduction, and hyperpigmentation treatment. Emphasize safe ingredients and gradual improvement.",
                        "rebuild_skin_barrier": "Provide barrier repair strategies. Focus on gentle, hydrating ingredients and avoiding further damage.",
                        "prevent_future_breakouts": "Explain maintenance strategies while healing. Balance treatment with prevention.",
                        "identify_safe_actives": "Guide on safe use of retinoids, acids, and other actives during recovery. Emphasize gradual introduction.",
                        "evidence_based_layering": "Provide evidence-based layering strategies for post-acne care. Focus on ingredient compatibility and efficacy."
                    }
                }
                
                # Intent category guidance
                intent_guidance = {
                    "functional": "Focus on effectiveness, performance, and practical results. Provide specific product recommendations with exact brand names, concentrations, and usage instructions. Include timing, application techniques, and expected results.",
                    "emotional": "Emphasize safety, gentleness, and peace of mind. Address concerns about side effects and skin sensitivity.",
                    "social": "Include expert recommendations, peer validation, and dermatologist-approved options. Reference trusted sources.",
                    "situational": "Address urgency and convenience factors. Provide quick solutions and immediate relief strategies.",
                    "risk_mitigation": "Highlight safety, testing, and side effect considerations. Emphasize gentle, tested formulations.",
                    "cognitive": "Provide research, data, and scientific evidence. Include clinical studies and evidence-based recommendations."
                }
                
                # Get specific guidance for this user's job-to-be-done
                job_guidance = segment_job_guidance.get(segment, {}).get(job_to_be_done, "Provide helpful, personalized advice based on the user's needs.")
                intent_guidance_text = intent_guidance.get(intent_category, "")
                
                enhanced_prompt = f"""
You are Cleen, an expert AI skincare assistant. Provide specific, actionable recommendations based on scientific research.

User Profile: {segment.replace('_', ' ')} with {intent_category} intent
User's Goal: {job_to_be_done.replace('_', ' ')}
Question: {request.query}

CRITICAL INSTRUCTIONS:
- Provide SPECIFIC product names, concentrations, and brands
- Give EXACT usage instructions with timing
- Include travel-friendly and workday integration tips
- DO NOT suggest consulting professionals - provide direct recommendations
- Be practical and actionable, not generic advice

Guidance for this user: {job_guidance}
Intent guidance: {intent_guidance_text}

Research Context:
{chr(10).join(context_chunks)}

Provide a detailed, specific answer with exact product recommendations:"""
                
                answer = gemini_llm.generate_answer(enhanced_prompt, [])
                logger.info(f"🔍 [QUERY-{query_id}] Segment-specific answer generated: {len(answer)} characters")
                
                # Extract URLs using improved regex from search results only
                if len(session["messages"]) <= 2:  # Only extract URLs for first question
                    logger.info(f"🔍 [QUERY-{query_id}] Using improved regex to extract URLs from {len(search_results)} search results...")
                    
                    # Extract URLs and filter for completeness
                    url_sources = []
                    for result in search_results:
                        url = extract_url_from_content(result["content"])
                        if url and url.startswith('http') and '.' in url.split('://')[1]:
                            # Validate URL completeness - must have proper domain structure
                            domain_part = url.split('://')[1].split('/')[0]
                            if '.' in domain_part and len(domain_part.split('.')[0]) > 0:
                                # Additional validation: domain must have at least 2 parts (e.g., doi.org, not just doi)
                                domain_parts = domain_part.split('.')
                                if len(domain_parts) >= 2 and len(domain_parts[0]) > 0 and len(domain_parts[1]) > 0:
                                    # Extra validation: DOI URLs must have more than just "/10" - must have actual DOI content
                                    if 'doi.org' in domain_part:
                                        # Check if DOI has more than just "/10" - must have actual DOI content
                                        path_part = url.split('://')[1].split('/', 1)[1] if '/' in url.split('://')[1] else ''
                                        if len(path_part) > 3:  # More than just "/10"
                                            url_sources.append({
                                                'url': url,
                                                'filename': result['filename'],
                                                'score': result.get('score', 0)
                                            })
                                            logger.info(f"🔍 [QUERY-{query_id}] Valid DOI URL extracted from {result['filename']}: {url}")
                                    else:
                                        # Non-DOI URLs - standard validation
                                        url_sources.append({
                                            'url': url,
                                            'filename': result['filename'],
                                            'score': result.get('score', 0)
                                        })
                                        logger.info(f"🔍 [QUERY-{query_id}] Valid URL extracted from {result['filename']}: {url}")
                    
                    # Sort by relevance score and take only top 2 URLs
                    url_sources.sort(key=lambda x: x['score'], reverse=True)
                    sources = [source['url'] for source in url_sources[:2]]  # Only top 2 URLs
                    
                    logger.info(f"🔍 [QUERY-{query_id}] Improved URL extraction completed: {len(sources)} valid URLs selected")
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
                    "intent_analysis": intent_analysis,
                    "user_segment": intent_analysis["primary_segment"],
                    "intent_category": intent_analysis["primary_intent_category"],
                    "job_to_be_done": intent_analysis["primary_job_to_be_done"]
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
                    "intent_analysis": intent_analysis,
                    "user_segment": intent_analysis["primary_segment"],
                    "intent_category": intent_analysis["primary_intent_category"],
                    "job_to_be_done": intent_analysis["primary_job_to_be_done"]
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
            
            # Add assistant response to session (no sources for chat context)
            add_message_to_session(session_id, "assistant", answer, [])
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"🔍 [QUERY-{query_id}] Query complete in {duration:.2f}s")
            
            return {
                "answer": answer,
                "sources": [],  # No sources when using chat context - normal conversation
                "search_results": [],
                "session_id": session_id,
                "used_documents": False,
                "used_chat_context": True,
                "intent_analysis": intent_analysis,
                "user_segment": intent_analysis["primary_segment"],
                "intent_category": intent_analysis["primary_intent_category"],
                "job_to_be_done": intent_analysis["primary_job_to_be_done"]
            }
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.error(f"🔍 [QUERY-{query_id}] ❌ Query failed after {duration:.2f}s: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)