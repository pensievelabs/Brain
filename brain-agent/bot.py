import os
import glob
import json
import shutil
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
AGENT_MD_PATH = os.path.join(AGENT_DIR, "agent.md")

# Similarity Threshold — gemini-embedding-001 cosine distances:
# 0.3-0.5 = strong match, 0.5-0.7 = moderate match, >0.8 = weak/unrelated
SIMILARITY_THRESHOLD = 0.75
# Max content snippet length injected into system prompt per search result
MAX_SNIPPET_CHARS = 500
# Max tool-call rounds per message
MAX_TOOL_ROUNDS = 5

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

def remove_from_index(filepath: str):
    """Removes a file from ChromaDB index."""
    try:
        collection.delete(ids=[filepath])
        logger.info(f"Removed index for {filepath}")
    except Exception as e:
        logger.error(f"Error removing index for {filepath}: {e}")

def semantic_search(query_text: str, n_results: int = 5):
    """
    Queries ChromaDB and returns (filepath, content_snippet) tuples.
    Filters out results above the similarity threshold.
    """
    try:
        query_embeddings = embedding_fn_query([query_text])
        
        results = collection.query(
            query_embeddings=query_embeddings,
            n_results=n_results,
            include=["documents", "distances", "metadatas"]
        )
        
        if not results or not results.get('distances') or not results['distances'][0]:
            return []
        
        distances = results['distances'][0]
        documents = results['documents'][0]
        ids = results['ids'][0]
        
        matched = []
        for dist, doc, file_id in zip(distances, documents, ids):
            if dist <= SIMILARITY_THRESHOLD:
                snippet = doc[:MAX_SNIPPET_CHARS] + ("..." if len(doc) > MAX_SNIPPET_CHARS else "")
                matched.append((file_id, snippet))
                logger.info(f"Semantic match: {file_id} (distance: {dist:.4f})")
            else:
                logger.info(f"Skipped: {file_id} (distance: {dist:.4f}, above threshold)")
        
        return matched
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

def list_vault_files(directory: str) -> str:
    """Lists all .md files under a subdirectory of the vault."""
    try:
        secure_path = get_secure_vault_path(directory)
        if not os.path.isdir(secure_path):
            return f"Not a directory: {secure_path}"
        files = glob.glob(os.path.join(secure_path, "**", "*.md"), recursive=True)
        rel_paths = [os.path.relpath(f, VAULT_DIR) for f in files]
        if not rel_paths:
            return "No .md files found."
        return "\n".join(sorted(rel_paths))
    except Exception as e:
        return f"Error listing files: {e}"

def move_vault_file(source_filepath: str, destination_filepath: str) -> str:
    """Moves a file from one vault location to another and updates the index."""
    try:
        secure_source = get_secure_vault_path(source_filepath)
        secure_dest = get_secure_vault_path(destination_filepath)
        
        if not os.path.exists(secure_source):
            return f"Source file not found: {secure_source}"
        
        os.makedirs(os.path.dirname(secure_dest), exist_ok=True)
        shutil.move(secure_source, secure_dest)
        
        # Update index: remove old, add new
        remove_from_index(secure_source)
        with open(secure_dest, "r", encoding="utf-8") as f:
            content = f.read()
        update_index(secure_dest, content)
        
        return f"Moved {secure_source} → {secure_dest}"
    except Exception as e:
        return f"Error moving file: {e}"

# Tool name → function mapping
TOOL_FUNCTIONS = {
    "read_vault_file": lambda args: read_vault_file(args.get("filepath", "")),
    "overwrite_vault_file": lambda args: overwrite_vault_file(args.get("filepath", ""), args.get("new_content", "")),
    "list_vault_files": lambda args: list_vault_files(args.get("directory", "")),
    "move_vault_file": lambda args: move_vault_file(args.get("source_filepath", ""), args.get("destination_filepath", "")),
}

tools = [
    {
        "type": "function",
        "function": {
            "name": "read_vault_file",
            "description": "Reads a markdown file from the vault and returns its content as a string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "The filepath to read from (absolute or relative to vault root)."
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
            "description": "Overwrites or creates a markdown file with new content and automatically updates the vector index. You MUST read the file first before overwriting to avoid clobbering existing content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "The filepath to write to (absolute or relative to vault root)."
                    },
                    "new_content": {
                        "type": "string",
                        "description": "The full markdown content of the file, including YAML frontmatter."
                    }
                },
                "required": ["filepath", "new_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_vault_files",
            "description": "Lists all .md files under a subdirectory of the vault. Use this to discover existing files when semantic search doesn't find a match. Example directories: '1-Projects', '2-Areas', '3-Resources', '4-Archives', 'Inbox'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "The subdirectory to list (e.g., '1-Projects' or '3-Resources/shower-thoughts')."
                    }
                },
                "required": ["directory"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_vault_file",
            "description": "Moves a file from one vault location to another. Use this for PARA tag evolution (e.g., moving a resource to projects). Updates the vector index automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_filepath": {
                        "type": "string",
                        "description": "Current filepath of the file to move."
                    },
                    "destination_filepath": {
                        "type": "string",
                        "description": "New filepath to move the file to."
                    }
                },
                "required": ["source_filepath", "destination_filepath"]
            }
        }
    }
]

# --- Telegram Bot Handlers ---

def build_system_prompt(search_results: list) -> str:
    """Builds the full system prompt with agent rules and semantic search context."""
    system_prompt = "You are BrainBot."
    try:
        if os.path.exists(AGENT_MD_PATH):
            with open(AGENT_MD_PATH, "r", encoding="utf-8") as f:
                system_prompt = f.read()
    except Exception as e:
        logger.error(f"Could not read agent.md: {e}")

    # Inject search results as content, not just paths
    if search_results:
        context_parts = ["## Vault Context (from semantic search)\n"]
        for filepath, snippet in search_results:
            rel_path = os.path.relpath(filepath, VAULT_DIR) if filepath.startswith(VAULT_DIR) else filepath
            context_parts.append(f"### File: `{rel_path}`\n```\n{snippet}\n```\n")
        context_str = "\n".join(context_parts)
        # Query-specific instructions for citation and source filtering
        context_str += (
            "\n## Query Response Instructions\n"
            "When answering a query, follow these rules strictly:\n"
            "1. Cite every vault file you reference using `📎 Source: [relative path]`.\n"
            "2. If you add information from your own training data beyond what the vault contains, "
            "put it under a `📚 Additional Context (not from your vault)` header. Never blend it silently.\n"
            "3. Exclude unvetted sources (Grokipedia, unmoderated wikis). Only cite authoritative, expert sources.\n"
            "4. Lead with vault content. Only supplement if the vault is incomplete or the user asks for more.\n"
        )
    else:
        context_str = "## Vault Context\nNo existing relevant files found in the vault."

    # Inject today's date
    from datetime import date
    today = date.today().isoformat()

    return f"{system_prompt}\n\n---\n**Today's date:** {today}\n**Vault root:** `{VAULT_DIR}`\n\n{context_str}"


async def execute_tool_calls(tool_calls, messages, model_name):
    """
    Executes tool calls and returns (final_content, modified_files).
    Supports multi-turn: up to MAX_TOOL_ROUNDS of sequential tool-call rounds.
    """
    modified_files = []
    
    for round_num in range(MAX_TOOL_ROUNDS):
        if not tool_calls:
            break
            
        logger.info(f"Tool round {round_num + 1}: {len(tool_calls)} call(s)")
        
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            try:
                function_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                function_args = {}
                
            logger.info(f"  → {function_name}({json.dumps(function_args)[:200]})")
            
            handler = TOOL_FUNCTIONS.get(function_name)
            if handler:
                result = handler(function_args)
                # Track modified files
                if function_name == "overwrite_vault_file":
                    modified_files.append(function_args.get("filepath", ""))
                elif function_name == "move_vault_file":
                    modified_files.append(function_args.get("destination_filepath", ""))
            else:
                result = f"Unknown function: {function_name}"
            
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": str(result),
            })
        
        # Ask the LLM to continue
        next_response = litellm.completion(
            model=model_name,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        next_message = next_response.choices[0].message
        
        if next_message.tool_calls:
            messages.append(next_message)
            tool_calls = next_message.tool_calls
        else:
            return next_message.content, modified_files
    
    # If we exhausted rounds, do a final call without tools
    final_response = litellm.completion(
        model=model_name,
        messages=messages,
    )
    return final_response.choices[0].message.content, modified_files


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming messages from the authorized user."""
    user_id = update.effective_user.id
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        logger.warning(f"Unauthorized access attempt from user {user_id}")
        return

    user_text = update.message.text or update.message.caption
    if not user_text:
        await update.message.reply_text("I can only process text right now.")
        return

    # Model routing
    # NOTE: swap to "gemini/gemini-3-flash-preview" when it stabilizes
    model_name = "gemini/gemini-2.5-flash"
    if user_text.startswith("/coach") or user_text.startswith("/explore"):
        model_name = "gemini/gemini-2.5-pro"

    # Semantic Search — inject content, not just paths
    logger.info("Running semantic search...")
    search_results = semantic_search(user_text)

    # Rolling context window (6 messages = 3 turns)
    if "chat_history" not in context.user_data:
        context.user_data["chat_history"] = []
        
    context.user_data["chat_history"].append({"role": "user", "content": user_text})
    
    if len(context.user_data["chat_history"]) > 6:
        context.user_data["chat_history"] = context.user_data["chat_history"][-6:]

    # Build system prompt with injected search content
    full_system_prompt = build_system_prompt(search_results)
    messages = [{"role": "system", "content": full_system_prompt}] + context.user_data["chat_history"]

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
            final_content, modified_files = await execute_tool_calls(
                response_message.tool_calls, messages, model_name
            )
        else:
            final_content = response_message.content
            modified_files = []

    except Exception as e:
        logger.error(f"LiteLLM or Tool execution error: {e}")
        await update.message.reply_text("Execution error.")
        return

    # Update chat history with assistant response
    if final_content:
        context.user_data["chat_history"].append({"role": "assistant", "content": final_content})

    # Reply
    if modified_files:
        file_list = ", ".join(os.path.basename(f) for f in modified_files)
        reply = f"📁 Done → {file_list}"
        if final_content:
            reply = final_content
    else:
        reply = final_content if final_content else "Executed."
        
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
