"""
Document processing module - replicates Onyx's exact approach
"""
import os
import uuid
import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from io import BytesIO
import tiktoken
from pydantic import BaseModel
import numpy as np

# Configure logging for document processor
logger = logging.getLogger(__name__)

# Onyx's exact configuration
DOC_EMBEDDING_CONTEXT_SIZE = 512  # Onyx's chunk size
CHUNK_OVERLAP = 0  # Onyx uses no overlap
EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v1"  # Onyx's model
EMBEDDING_DIM = 768  # Onyx's embedding dimension

class DocumentChunk(BaseModel):
    """Represents a document chunk with metadata"""
    content: str
    token_count: int
    embedding: List[float]
    metadata: Dict[str, Any]

class DocumentProcessor:
    """Processes documents using Onyx's exact approach"""
    
    def __init__(self):
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
    def _simple_chunk_text(self, text: str, chunk_size: int = DOC_EMBEDDING_CONTEXT_SIZE) -> List[str]:
        """Simple text chunking by sentences and token count"""
        # Split by sentences first
        sentences = re.split(r'[.!?]+', text)
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # Check if adding this sentence would exceed chunk size
            test_chunk = current_chunk + " " + sentence if current_chunk else sentence
            token_count = len(self.tokenizer.encode(test_chunk))
            
            if token_count > chunk_size and current_chunk:
                # Current chunk is full, save it and start new one
                chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                # Add sentence to current chunk
                current_chunk = test_chunk
        
        # Add the last chunk if it has content
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
            
        return chunks
    
    def generate_query_embedding(self, query: str) -> List[float]:
        """Generate embedding for a search query"""
        try:
            # Use nomic-ai API via HTTP requests
            import requests
            
            nomic_api_key = os.getenv("NOMIC_API_KEY")
            if not nomic_api_key:
                raise ValueError("NOMIC_API_KEY not found")
            
            # Call nomic-ai API
            url = "https://api-atlas.nomic.ai/v1/embedding/text"
            headers = {
                "Authorization": f"Bearer {nomic_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "texts": [query],
                "model": "nomic-embed-text-v1"
            }
            
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            embedding = result['embeddings'][0]
            
            logger.info(f"Generated query embedding using {EMBEDDING_MODEL}")
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating nomic-ai query embedding: {e}")
            logger.warning("Falling back to hash-based query embedding")
            
            # Fallback to hash-based embedding
            import hashlib
            hash_obj = hashlib.md5(query.encode())
            hash_bytes = hash_obj.digest()
            # Convert to 768-dimensional vector
            embedding = []
            for i in range(EMBEDDING_DIM):
                byte_idx = i % len(hash_bytes)
                embedding.append(float(hash_bytes[byte_idx]) / 255.0)
            return embedding
    
    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        try:
            # Use nomic-ai API via HTTP requests
            import requests
            
            nomic_api_key = os.getenv("NOMIC_API_KEY")
            if not nomic_api_key:
                raise ValueError("NOMIC_API_KEY not found")
            
            # Call nomic-ai API
            url = "https://api-atlas.nomic.ai/v1/embedding/text"
            headers = {
                "Authorization": f"Bearer {nomic_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "texts": texts,
                "model": "nomic-embed-text-v1"
            }
            
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            embeddings = result['embeddings']
            
            logger.info(f"Generated {len(embeddings)} real embeddings using {EMBEDDING_MODEL}")
            return embeddings
            
        except Exception as e:
            logger.error(f"Error generating nomic-ai embeddings: {e}")
            logger.warning("Falling back to hash-based embeddings")
            
            # Fallback to hash-based embeddings
            embeddings = []
            for text in texts:
                import hashlib
                hash_obj = hashlib.md5(text.encode())
                hash_bytes = hash_obj.digest()
                # Convert to 768-dimensional vector
                embedding = []
                for i in range(EMBEDDING_DIM):
                    byte_idx = i % len(hash_bytes)
                    embedding.append(float(hash_bytes[byte_idx]) / 255.0)
                embeddings.append(embedding)
            return embeddings
    
    def _extract_text_from_pdf(self, file_content: bytes) -> str:
        """Extract text from PDF"""
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(file_content))
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            print(f"Error extracting PDF text: {e}")
            return ""
    
    def _extract_text_from_docx(self, file_content: bytes) -> str:
        """Extract text from DOCX"""
        try:
            from docx import Document as DocxDocument
            doc = DocxDocument(BytesIO(file_content))
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except Exception as e:
            print(f"Error extracting DOCX text: {e}")
            return ""
    
    def _extract_text_from_txt(self, file_content: bytes) -> str:
        """Extract text from plain text files"""
        try:
            return file_content.decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"Error extracting text: {e}")
            return ""
    
    def _extract_text(self, file_content: bytes, filename: str) -> str:
        """Extract text from various file formats"""
        ext = os.path.splitext(filename)[1].lower()
        
        if ext == ".pdf":
            return self._extract_text_from_pdf(file_content)
        elif ext == ".docx":
            return self._extract_text_from_docx(file_content)
        elif ext in [".txt", ".md", ".json", ".csv"]:
            return self._extract_text_from_txt(file_content)
        else:
            # Try to decode as text for unknown formats
            return self._extract_text_from_txt(file_content)
    
    def process_document(self, file_content: bytes, filename: str) -> List[DocumentChunk]:
        """Process a document and return chunks with embeddings - with detailed logging"""
        process_id = str(uuid.uuid4())[:8]
        start_time = datetime.now()
        
        logger.info(f"📄 [PROCESS-{process_id}] Starting document processing: {filename}")
        logger.info(f"📄 [PROCESS-{process_id}] File size: {len(file_content)} bytes")
        
        try:
            # Extract text
            logger.info(f"📄 [PROCESS-{process_id}] Extracting text content...")
            text_content = self._extract_text(file_content, filename)
            logger.info(f"📄 [PROCESS-{process_id}] Text extracted: {len(text_content)} characters")
            
            if not text_content.strip():
                logger.warning(f"📄 [PROCESS-{process_id}] ⚠️ No text content found in {filename}")
                return []
            
            # Clean text
            logger.info(f"📄 [PROCESS-{process_id}] Cleaning text...")
            text_content = re.sub(r'\s+', ' ', text_content).strip()
            logger.info(f"📄 [PROCESS-{process_id}] Text cleaned: {len(text_content)} characters")
            
            # Chunk the text
            logger.info(f"📄 [PROCESS-{process_id}] Starting text chunking...")
            chunks_text = self._simple_chunk_text(text_content)
            logger.info(f"📄 [PROCESS-{process_id}] Text chunked: {len(chunks_text)} chunks created")
            
            if not chunks_text:
                logger.warning(f"📄 [PROCESS-{process_id}] ⚠️ No chunks created from {filename}")
                return []
            
            # Log chunk details
            total_tokens = 0
            for i, chunk in enumerate(chunks_text):
                token_count = len(self.tokenizer.encode(chunk))
                total_tokens += token_count
                logger.info(f"📄 [PROCESS-{process_id}] Chunk {i+1}: {token_count} tokens, {len(chunk)} chars")
                logger.info(f"📄 [PROCESS-{process_id}] Chunk {i+1} preview: {chunk[:100]}...")
            
            # Generate embeddings for all chunks
            logger.info(f"📄 [PROCESS-{process_id}] Generating embeddings...")
            embeddings = self._generate_embeddings(chunks_text)
            logger.info(f"📄 [PROCESS-{process_id}] Embeddings generated: {len(embeddings)} vectors")
            
            # Create DocumentChunk objects
            logger.info(f"📄 [PROCESS-{process_id}] Creating document chunks...")
            chunks = []
            for i, (chunk_text, embedding) in enumerate(zip(chunks_text, embeddings)):
                token_count = len(self.tokenizer.encode(chunk_text))
                
                chunk = DocumentChunk(
                    content=chunk_text,
                    token_count=token_count,
                    embedding=embedding,
                    metadata={
                        "filename": filename,
                        "chunk_index": i,
                        "total_chunks": len(chunks_text)
                    }
                )
                chunks.append(chunk)
                logger.info(f"📄 [PROCESS-{process_id}] Created chunk {i+1}: {token_count} tokens")
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info(f"📄 [PROCESS-{process_id}] Document processing complete!")
            logger.info(f"📄 [PROCESS-{process_id}] Summary: {len(chunks)} chunks, {total_tokens} total tokens")
            logger.info(f"📄 [PROCESS-{process_id}] Processing time: {duration:.2f} seconds")
            
            return chunks
            
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.error(f"📄 [PROCESS-{process_id}] ❌ Document processing failed after {duration:.2f}s: {str(e)}")
            return []

# Global instance
document_processor = DocumentProcessor()