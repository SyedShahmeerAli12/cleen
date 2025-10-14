"""
Vespa integration for hybrid search (keyword + vector)
"""
import json
import httpx
from typing import List, Dict, Any, Optional
from document_processor import DocumentChunk

class VespaClient:
    def __init__(self, host: str = "index", port: int = 8081):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        
    async def is_ready(self) -> bool:
        """Check if Vespa is ready"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/ApplicationStatus")
                return response.status_code == 200
        except:
            return False
    
    async def store_document(self, chunk: DocumentChunk, doc_id: str) -> bool:
        """Store a document chunk in Vespa"""
        try:
            # Create Vespa document
            vespa_doc = {
                "fields": {
                    "id": doc_id,
                    "content": chunk.content,
                    "embedding": chunk.embedding,
                    "filename": chunk.metadata.get("filename", ""),
                    "token_count": chunk.token_count,
                    "chunk_index": chunk.metadata.get("chunk_index", 0),
                    "total_chunks": chunk.metadata.get("total_chunks", 1)
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/document/v1/personal_rag/document/docid/{doc_id}",
                    json=vespa_doc,
                    headers={"Content-Type": "application/json"}
                )
                return response.status_code in [200, 201]
        except Exception as e:
            print(f"Error storing document {doc_id}: {e}")
            return False
    
    async def hybrid_search(self, query: str, query_embedding: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """Perform hybrid search (keyword + vector)"""
        try:
            # Create Vespa query
            vespa_query = {
                "yql": "select * from document where ({targetHits:10}nearestNeighbor(embedding,query_vector)) or userQuery()",
                "hits": limit,
                "ranking": "default",
                "input.query(query_vector)": query_embedding,
                "query": query
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/search/",
                    json=vespa_query,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    hits = result.get("root", {}).get("children", [])
                    
                    # Extract relevant information
                    search_results = []
                    for hit in hits:
                        fields = hit.get("fields", {})
                        search_results.append({
                            "content": fields.get("content", ""),
                            "filename": fields.get("filename", ""),
                            "relevance": hit.get("relevance", 0.0),
                            "token_count": fields.get("token_count", 0)
                        })
                    
                    return search_results
                else:
                    print(f"Vespa search error: {response.status_code}")
                    return []
        except Exception as e:
            print(f"Error in hybrid search: {e}")
            return []
    
    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document from Vespa"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.base_url}/document/v1/personal_rag/document/docid/{doc_id}"
                )
                return response.status_code in [200, 404]  # 404 means already deleted
        except Exception as e:
            print(f"Error deleting document {doc_id}: {e}")
            return False

# Global instance
vespa_client = VespaClient()
