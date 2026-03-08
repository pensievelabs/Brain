import os
import glob
import logging
from pathlib import Path
import chromadb
from chromadb.utils.embedding_functions import GoogleGenerativeAiEmbeddingFunction
from dotenv import load_dotenv

# --- Logging ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.error("Missing GEMINI_API_KEY in environment variables.")
    exit(1)

VAULT_DIR = os.path.expanduser("~/Documents/Brain/vault")
AGENT_DIR = os.path.expanduser("~/Documents/Brain/brain-agent")
CHROMA_DB_DIR = os.path.join(AGENT_DIR, "chroma_db")

# --- ChromaDB Setup ---
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_DIR)

embedding_fn_document = GoogleGenerativeAiEmbeddingFunction(
    api_key=GEMINI_API_KEY,
    task_type="RETRIEVAL_DOCUMENT",
    model_name="models/gemini-embedding-001"
)

collection = chroma_client.get_or_create_collection(
    name="vault_notes",
    embedding_function=embedding_fn_document
)

def index_vault():
    """Scans ~/vault/**/*.md and upserts into ChromaDB."""
    logger.info(f"Scanning {VAULT_DIR} for markdown files...")
    files_to_index = glob.glob(os.path.join(VAULT_DIR, "**", "*.md"), recursive=True)
    
    total_files = len(files_to_index)
    logger.info(f"Found {total_files} files to index.")
    
    for i, filepath in enumerate(files_to_index):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Simple content check
            if not content.strip():
                logger.warning(f"Skipping empty file: {filepath}")
                continue
                
            collection.upsert(
                documents=[content],
                metadatas=[{"filepath": filepath}],
                ids=[filepath]
            )
            if (i + 1) % 10 == 0 or (i + 1) == total_files:
                logger.info(f"Indexed {i + 1}/{total_files} files...")
        except Exception as e:
            logger.error(f"Error indexing {filepath}: {e}")
            
    logger.info("Finished re-indexing vault.")

if __name__ == "__main__":
    index_vault()
