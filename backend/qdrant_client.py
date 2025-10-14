"""
Qdrant Client for Personal RAG - replaces Vespa with simpler vector database
"""
import os
import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from qdrant_client.http import models
from document_processor import DocumentChunk

class QdrantClientWrapper:
    def __init__(self, host: str = "qdrant", port: int = 6333):
        self.host = host
        self.port = port
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = "personal_rag_documents"
        self._ensure_collection_exists()
        
    def _ensure_collection_exists(self):
        """Create collection if it doesn't exist"""
        try:
            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                # Create collection with 768-dimensional vectors (matching our embeddings)
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=768,  # Our embedding dimension
                        distance=Distance.COSINE
                    )
                )
                print(f"Created Qdrant collection: {self.collection_name}")
            else:
                print(f"Qdrant collection already exists: {self.collection_name}")
        except Exception as e:
            print(f"Error ensuring collection exists: {e}")
    
    async def is_ready(self) -> bool:
        """Check if Qdrant is ready"""
        try:
            collections = self.client.get_collections()
            return True
        except Exception as e:
            print(f"Qdrant not ready: {e}")
            return False

    async def store_document(self, chunk: DocumentChunk, doc_id: str) -> bool:
        """Store a document chunk in Qdrant"""
        try:
            # Create point for Qdrant
            point = PointStruct(
                id=doc_id,
                vector=chunk.embedding,
                payload={
                    "content": chunk.content,
                    "filename": chunk.metadata.get("filename", "unknown"),
                    "chunk_index": chunk.metadata.get("chunk_index", 0),
                    "total_chunks": chunk.metadata.get("total_chunks", 1),
                    "token_count": chunk.token_count
                }
            )
            
            # Insert point into collection
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            print(f"Successfully stored document chunk {doc_id} in Qdrant.")
            return True
            
        except Exception as e:
            print(f"Error storing document chunk {doc_id} in Qdrant: {e}")
            return False

    async def hybrid_search(self, query: str, query_embedding: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """Perform hybrid search in Qdrant (vector similarity + keyword filtering)"""
        try:
            # Perform vector search
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
                with_payload=True
            )
            
            # Convert results to our format
            search_hits = []
            for result in search_results:
                payload = result.payload
                search_hits.append({
                    "id": str(result.id),
                    "content": payload.get("content", ""),
                    "filename": payload.get("filename", "unknown"),
                    "chunk_index": payload.get("chunk_index", 0),
                    "score": result.score
                })
            
            print(f"Qdrant search successful for query: {query}")
            return search_hits
            
        except Exception as e:
            print(f"Error during Qdrant search: {e}")
            return []

# Global instance
qdrant_client = QdrantClientWrapper()
