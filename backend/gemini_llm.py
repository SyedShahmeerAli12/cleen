"""
Gemini LLM integration for Personal RAG
"""
import os
import google.generativeai as genai
from typing import List, Dict, Any

class GeminiLLM:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key not provided")
        
        genai.configure(api_key=self.api_key)
        
        # Use the working model from your test
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")
        print("Successfully loaded model: models/gemini-2.5-flash")
    
    def generate_answer(self, query: str, context_chunks: List[str] = None) -> str:
        """Generate answer using Gemini with optional context"""
        try:
            if context_chunks:
                # Create context from chunks
                context = "\n\n".join(context_chunks)
                prompt = f"""Based on the context below, answer the question concisely.

Context:
{context}

Question: {query}

Answer briefly (max 100 words):"""
            else:
                # Simple query without context
                prompt = f"Answer briefly (max 50 words): {query}"
            
            response = self.model.generate_content(prompt)
            return response.text
            
        except Exception as e:
            return f"Error generating answer: {str(e)}"
    
    def generate_summary(self, text: str) -> str:
        """Generate summary of text using Gemini"""
        try:
            prompt = f"Please provide a concise summary of the following text:\n\n{text}"
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error generating summary: {str(e)}"

# Global instance
gemini_llm = GeminiLLM(api_key="AIzaSyBCOeL_Tele48KJAq4tJs7HId9Fh5ai24E")
