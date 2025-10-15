"""
Dedicated Document Indexing Service
Runs separately from backend, monitors documents folder, indexes only new/changed files
Now with persistent storage to avoid re-indexing on restart
"""
import os
import time
import hashlib
import json
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
    def __init__(self, docs_dir: str = "/app/data/documents", state_dir: str = "/app/indexer_state"):
        self.docs_dir = Path(docs_dir)
        self.state_dir = Path(state_dir)
        self.state_file = self.state_dir / "processed_files.json"
        self.processed_files: Dict[str, str] = {}  # filename -> file_hash
        self.supported_exts = {".pdf", ".docx", ".txt", ".md", ".json", ".csv"}
        
        # Create state directory if it doesn't exist
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # Load previously processed files
        self.load_processed_files()
    
    def load_processed_files(self):
        """Load previously processed files from persistent storage"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    self.processed_files = json.load(f)
                logger.info(f"📁 Loaded {len(self.processed_files)} previously processed files")
            else:
                logger.info("📁 No previous state found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading processed files state: {e}")
            self.processed_files = {}
    
    def save_processed_files(self):
        """Save processed files state to persistent storage"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.processed_files, f, indent=2)
            logger.debug(f"💾 Saved state for {len(self.processed_files)} processed files")
        except Exception as e:
            logger.error(f"Error saving processed files state: {e}")
        
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
            
            # Save state to persistent storage
            self.save_processed_files()
            
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
        
        # Check if Qdrant already has data and we have processed files
        try:
            point_count = qdrant_client.get_point_count()
            if point_count > 0 and len(self.processed_files) > 0:
                logger.info(f"📊 Qdrant already has {point_count} vectors and {len(self.processed_files)} files tracked")
                logger.info("📁 Checking for new or changed files only...")
        except Exception as e:
            logger.warning(f"Could not check Qdrant status: {e}")
        
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
