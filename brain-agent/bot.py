import os
import glob
import json
import logging
from pathlib import Path
import nest_asyncio
import chromadb
from chromadb.utils.embedding_functions import GoogleGenerativeAiEmbeddingFunction
import litellm
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Apply nest_asyncio for compatible nested event loops if needed by underlying libraries
nest_asyncio.apply()

# --- Logging ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration & Setup ---
ALLOWED_USER_ID = os.environ.get("ALLOWED_USER_ID")
if ALLOWED_USER_ID:
    ALLOWED_USER_ID = int(ALLOWED_USER_ID)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not all([ALLOWED_USER_ID, TELEGRAM_BOT_TOKEN, GEMINI_API_KEY]):
    logger.error("Missing required environment variables: ALLOWED_USER_ID, TELEGRAM_BOT_TOKEN, GEMINI_API_KEY")

VAULT_DIR = os.path.expanduser("~/Documents/Brain/vault")
AGENT_DIR = os.path.expanduser("~/Documents/Brain/brain-agent")
CHROMA_DB_DIR = os.path.join(AGENT_DIR, "chroma_db")
AGENTS_MD_PATH = os.path.join(AGENT_DIR, "AGENTS.md")

# Similarity Threshold (Threshold for cosine/L2 distance metric).
# Adjust this constant based on testing. text-embedding-004 distance typically indicates semantic distance.
SIMILARITY_THRESHOLD = 0.5

# --- ChromaDB Setup ---
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_DIR)

embedding_fn_document = GoogleGenerativeAiEmbeddingFunction(
    api_key=GEMINI_API_KEY,
    task_type="RETRIEVAL_DOCUMENT",
    model_name="models/gemini-embedding-001"
)

embedding_fn_query = GoogleGenerativeAiEmbeddingFunction(
    api_key=GEMINI_API_KEY,
    task_type="RETRIEVAL_QUERY",
    model_name="models/gemini-embedding-001"
)

collection = chroma_client.get_or_create_collection(
    name="vault_notes",
    embedding_function=embedding_fn_document
)

# --- Vault & ChromaDB Functions ---

async def index_vault():
    """Scans ~/vault/**/*.md and upserts into ChromaDB."""
    logger.info("Starting index_vault...")
    files_to_index = glob.glob(os.path.join(VAULT_DIR, "**", "*.md"), recursive=True)
    
    for filepath in files_to_index:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            collection.upsert(
                documents=[content],
                metadatas=[{"filepath": filepath}],
                ids=[filepath]
            )
        except Exception as e:
            logger.error(f"Error indexing {filepath}: {e}")
    logger.info(f"Finished indexing {len(files_to_index)} files.")

def update_index(filepath: str, content: str):
    """Upserts a single file into ChromaDB immediately after modification."""
    try:
        collection.upsert(
            documents=[content],
            metadatas=[{"filepath": filepath}],
            ids=[filepath]
        )
        logger.info(f"Updated index for {filepath}")
    except Exception as e:
        logger.error(f"Error updating index for {filepath}: {e}")

def semantic_search(query_text: str, n_results: int = 2):
    """
    Queries ChromaDB and evaluates the distances array.
    If the top result's distance > SIMILARITY_THRESHOLD (weak match),
    returns an empty list []. Otherwise, returns the filepaths.
    """
    try:
        # Generate embeddings explicitly if required or use the query function
        query_embeddings = embedding_fn_query([query_text])
        
        results = collection.query(
            query_embeddings=query_embeddings,
            n_results=n_results
        )
        
        if not results or not results.get('distances') or not results['distances'][0]:
            return []
        
        distances = results['distances'][0]
        ids = results['ids'][0]
        
        top_distance = distances[0]
        logger.info(f"Top semantic search distance: {top_distance}")
        
        if top_distance > SIMILARITY_THRESHOLD:
            logger.info("Top result distance is above threshold; indicating weak semantic match.")
            return []
            
        return ids
    except Exception as e:
        logger.error(f"Error in semantic search: {e}")
        return []

# --- LLM Tools ---

def get_secure_vault_path(filepath: str) -> str:
    """Ensures everything falls strictly within VAULT_DIR to prevent path traversal issues."""
    filepath = os.path.expanduser(filepath)
    if os.path.isabs(filepath):
        if not filepath.startswith(VAULT_DIR):
            filepath = os.path.join(VAULT_DIR, filepath.lstrip("/"))
    else:
        filepath = os.path.join(VAULT_DIR, filepath)
        
    real_vault_dir = os.path.realpath(VAULT_DIR)
    real_filepath = os.path.realpath(filepath)
    
    if not real_filepath.startswith(real_vault_dir):
        raise ValueError(f"Path outside vault: {filepath}")
        
    return real_filepath

def read_vault_file(filepath: str) -> str:
    """Takes a filepath, reads the markdown file, and returns the content."""
    try:
        secure_path = get_secure_vault_path(filepath)
        with open(secure_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

def overwrite_vault_file(filepath: str, new_content: str) -> str:
    """Overwrites existing file at filepath and calls update_index()."""
    try:
        secure_path = get_secure_vault_path(filepath)
        os.makedirs(os.path.dirname(secure_path), exist_ok=True)
        with open(secure_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        update_index(secure_path, new_content)
        return f"Successfully saved to {secure_path}"
    except Exception as e:
        return f"Error writing file: {e}"

tools = [
    {
        "type": "function",
        "function": {
            "name": "read_vault_file",
            "description": "Reads a markdown file from the vault and returns its content as a string. Analyzes existing tags and structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "The absolute filepath to read from."
                    }
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "overwrite_vault_file",
            "description": "Overwrites/creates a regular markdown file with new synthesized content (including PARA YAML tags) and automatically updates the vector index.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "The absolute filepath to overwrite or create."
                    },
                    "new_content": {
                        "type": "string",
                        "description": "The new full markdown content of the file."
                    }
                },
                "required": ["filepath", "new_content"]
            }
        }
    }
]

# --- Telegram Bot Handlers ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming messages from the authorized user."""
    user_id = update.effective_user.id
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        logger.warning(f"Unauthorized access attempt from user {user_id}")
        return

    # Treat text or caption (from audio)
    user_text = update.message.text or update.message.caption
    if not user_text:
        await update.message.reply_text("I can only process text right now.")
        return

    # Routing
    model_name = "gemini/gemini-3.1-flash-lite-preview"
    if user_text.startswith("/coach") or user_text.startswith("/explore"):
        model_name = "gemini/gemini-3.1-pro-preview"

    # Semantic Search
    logger.info("Running semantic search...")
    search_results = semantic_search(user_text)

    if "chat_history" not in context.user_data:
        context.user_data["chat_history"] = []
        
    context.user_data["chat_history"].append({"role": "user", "content": user_text})
    
    if len(context.user_data["chat_history"]) > 6:
        context.user_data["chat_history"] = context.user_data["chat_history"][-6:]

    system_prompt = "You are BrainBot."
    try:
        if os.path.exists(AGENTS_MD_PATH):
            with open(AGENTS_MD_PATH, "r", encoding="utf-8") as f:
                system_prompt = f.read()
    except Exception as e:
        logger.error(f"Could not read AGENTS.md: {e}")

    context_str = ""
    if search_results:
        context_str = "Relevant existing file paths found in vault:\n" + "\n".join(search_results)
    else:
        context_str = "No existing relevant context was found."

    full_system_prompt = f"{system_prompt}\n\nSystem Context based on latest user message:\n{context_str}"

    messages = [{"role": "system", "content": full_system_prompt}] + context.user_data["chat_history"]

    modified_files = []

    logger.info(f"Calling LiteLLM with model: {model_name}")
    try:
        response = litellm.completion(
            model=model_name,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        response_message = response.choices[0].message
        
        if response_message.tool_calls:
            messages.append(response_message)
            
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    function_args = {}
                    
                logger.info(f"LLM called tool: {function_name}")
                
                if function_name == "read_vault_file":
                    result = read_vault_file(function_args.get("filepath", ""))
                elif function_name == "overwrite_vault_file":
                    fp = function_args.get("filepath", "")
                    content = function_args.get("new_content", "")
                    result = overwrite_vault_file(fp, content)
                    modified_files.append(os.path.basename(fp))
                else:
                    result = f"Unknown function {function_name}"
                    
                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": str(result),
                    }
                )
            
            second_response = litellm.completion(
                model=model_name,
                messages=messages,
            )
            final_content = second_response.choices[0].message.content
        else:
            final_content = response_message.content

    except Exception as e:
        logger.error(f"LiteLLM or Tool execution error: {e}")
        await update.message.reply_text("Execution error.")
        return

    if final_content:
        context.user_data["chat_history"].append({"role": "assistant", "content": final_content})

    if modified_files:
        reply = f"System state confirmed. Files modified: {', '.join(modified_files)}"
    else:
        reply = final_content if final_content else "System state confirmed. Executed silently."
        
    await update.message.reply_text(reply)

# --- Main Application ---

async def on_startup(application: Application):
    """Run initial indexing asynchronously upon startup."""
    asyncio.create_task(index_vault())

def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("No TELEGRAM_BOT_TOKEN provided.")
        return
        
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(on_startup).build()
    application.add_handler(MessageHandler(filters.TEXT | filters.AUDIO | filters.VOICE, handle_message))
    
    logger.info("BrainBot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
