"""
Dedicated Document Indexing Service
Runs separately from backend, monitors documents folder, indexes only new/changed files
"""
import os
import time
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Set
from document_processor import document_processor
from qdrant_wrapper import qdrant_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - INDEXER - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/app/logs/indexer.log')
    ]
)
logger = logging.getLogger(__name__)

# Create logs directory
os.makedirs('/app/logs', exist_ok=True)

class DocumentIndexer:
    def __init__(self, docs_dir: str = "/app/data/documents"):
        self.docs_dir = Path(docs_dir)
        self.processed_files: Dict[str, str] = {}  # filename -> file_hash
        self.supported_exts = {".pdf", ".docx", ".txt", ".md", ".json", ".csv"}
        
    def get_file_hash(self, file_path: Path) -> str:
        """Get MD5 hash of file content"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"Error getting hash for {file_path}: {e}")
            return ""
    
    def is_file_changed(self, file_path: Path) -> bool:
        """Check if file has changed since last processing"""
        filename = file_path.name
        current_hash = self.get_file_hash(file_path)
        
        if filename not in self.processed_files:
            return True  # New file
        
        if self.processed_files[filename] != current_hash:
            return True  # File changed
        
        return False  # File unchanged
    
    async def index_file(self, file_path: Path) -> bool:
        """Index a single file"""
        filename = file_path.name
        logger.info(f"📄 Indexing: {filename}")
        
        try:
            # Get file hash
            file_hash = self.get_file_hash(file_path)
            
            # Read file content
            with open(file_path, 'rb') as f:
                content = f.read()
            
            logger.info(f"📄 File size: {len(content)} bytes")
            
            # Process document
            chunks = document_processor.process_document(content, filename)
            logger.info(f"📄 Created {len(chunks)} chunks")
            
            # Store chunks in Qdrant
            stored_count = 0
            for i, chunk in enumerate(chunks):
                deterministic_id = f"{filename}_{i}"
                success = await qdrant_client.store_document(chunk, deterministic_id)
                if success:
                    stored_count += 1
            
            # Update processed files record
            self.processed_files[filename] = file_hash
            
            logger.info(f"📄 ✅ Indexed {filename}: {stored_count}/{len(chunks)} chunks stored")
            return True
            
        except Exception as e:
            logger.error(f"📄 ❌ Failed to index {filename}: {e}")
            return False
    
    async def scan_and_index(self):
        """Scan documents directory and index new/changed files"""
        if not self.docs_dir.exists():
            logger.warning(f"📁 Documents directory not found: {self.docs_dir}")
            return
        
        logger.info(f"📁 Scanning: {self.docs_dir}")
        
        # Find all supported files
        files_to_process = []
        for file_path in self.docs_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.supported_exts:
                if self.is_file_changed(file_path):
                    files_to_process.append(file_path)
        
        if not files_to_process:
            logger.info("📁 No new or changed files found")
            return
        
        logger.info(f"📁 Found {len(files_to_process)} files to process: {[f.name for f in files_to_process]}")
        
        # Process each file
        for file_path in files_to_process:
            await self.index_file(file_path)
    
    def run_continuous(self, scan_interval: int = 30):
        """Run continuous monitoring"""
        logger.info("🚀 Starting continuous document indexing service")
        logger.info(f"📁 Monitoring: {self.docs_dir}")
        logger.info(f"⏰ Scan interval: {scan_interval} seconds")
        
        import asyncio
        
        async def async_loop():
            while True:
                try:
                    await self.scan_and_index()
                    await asyncio.sleep(scan_interval)
                except KeyboardInterrupt:
                    logger.info("🛑 Indexing service stopped")
                    break
                except Exception as e:
                    logger.error(f"💥 Indexing service error: {e}")
                    await asyncio.sleep(scan_interval)
        
        asyncio.run(async_loop())

if __name__ == "__main__":
    indexer = DocumentIndexer()
    indexer.run_continuous()
