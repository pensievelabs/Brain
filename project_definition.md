# Project: Headless Second Brain (macOS/Debian + Telegram + local Obsidian)

## System Overview
A headless AI agent currently developed on macOS, targeting Debian deployment. Acts as an autonomous Chief of Staff that receives text via Telegram, classifies semantic intent, and manages an Obsidian vault using the PARA method. Features a Propose → Confirm → Act protocol for vault mutations, semantic search via ChromaDB, and specialized `/coach` and `/explore` modes.

Uses a **modular, interface-driven architecture** — messaging, LLM, memory, and vault operations are defined by ABCs and can be swapped independently. A central Orchestrator routes messages, chains tools, and coordinates workflows.

## Directory Structure

~/brain-agent/
├── bot.py                       # Thin entrypoint — wires components and starts
├── config.py                    # Centralized env vars, paths, model names
├── agent.md                     # Master orchestrator prompt
├── BotDesign.md                 # Architecture design reference
├── interfaces/                  # ABCs: MessagingTransport, LLMProvider, MemoryBackend
├── transports/                  # Telegram implementation (swappable for Slack, CLI)
├── providers/                   # Gemini/LiteLLM implementation (per-module LLM config)
├── memory/                      # ChromaDB implementation (swappable for Pinecone, etc.)
├── vault/                       # VaultManager: secure file ops + tool schemas
├── orchestrator/                # Central brain: search → prompt → LLM → tools → response
├── modules/                     # Capability modules
│   └── task_scheduler.py        # Reading queue bankruptcy protocol
├── prompts/                     # Per-module system prompts (classifier, coach, explore)
├── briefing.py                  # Daily cron script for morning summaries
├── chroma_db/                   # ChromaDB persistent vector store
└── requirements.txt

~/vault/
├── 1-Projects/           # Active projects (#project)
├── 2-Areas/              # Ongoing responsibilities (#area)
├── 3-Resources/          # Interests, research, shower thoughts (#resource)
├── 4-Archives/           # Completed/inactive items (#archive)
├── Inbox/                # Default drop zone for unclassified items
└── Instructions.md       # Vault meta-documentation

## Component Specifications

### 1. Interfaces Layer
ABC contracts that make the system pluggable:
* **MessagingTransport** (`interfaces/messaging.py`) — `start()`, `send()`, `stop()`. Any platform implements this.
* **LLMProvider** (`interfaces/llm.py`) — `complete()` returning `LLMResponse`. Each module gets its own instance.
* **MemoryBackend** (`interfaces/memory.py`) — `index_all()`, `upsert()`, `remove()`, `search()`. Returns `SearchResult` objects.

### 2. Orchestrator (`orchestrator/orchestrator.py`)
Central brain — transport-agnostic. Receives `(user_id, text)`, returns response string.
* Runs semantic search via `MemoryBackend`
* Builds system prompt from `agent.md` + search context + date
* Routes to `DEFAULT_MODEL` or `PRO_MODEL` based on `/coach` and `/explore` commands
* Executes multi-turn tool calls (up to `MAX_TOOL_ROUNDS`)
* Manages per-user rolling chat history (6-message sliding window)
* All sync operations wrapped in `asyncio.to_thread()` to avoid blocking

### 3. Telegram Transport (`transports/telegram_transport.py`)
* Implements `MessagingTransport` using `python-telegram-bot`
* Handles user auth (`ALLOWED_USER_ID`), message extraction, reply delivery
* Swappable for Slack, CLI, Discord without touching business logic

### 4. Gemini Provider (`providers/gemini_provider.py`)
* Implements `LLMProvider` using `litellm`
* Constructed with model name and optional system prompt
* Model names configured in `config.py` (overridable via env vars)
* Models: `DEFAULT_MODEL` (default: `gemini/gemini-2.5-flash`), `PRO_MODEL` (default: `gemini/gemini-2.5-pro`)

### 5. ChromaDB Memory (`memory/chroma_memory.py`)
* Implements `MemoryBackend` using ChromaDB + `gemini-embedding-001`
* Dual task types: `RETRIEVAL_DOCUMENT` for indexing, `RETRIEVAL_QUERY` for search
* Similarity threshold filtering (default: 0.75)

### 6. Vault Manager (`vault/vault_tools.py`)
* Secure file operations with path traversal prevention
* Tools: `read_vault_file`, `overwrite_vault_file`, `list_vault_files`, `move_vault_file`, `create_reading_stub`, `append_to_file`
* Auto-updates vector index on file mutations
* Provides tool schemas for LLM function calling
* `create_reading_stub` generates independent reading queue files in `3-Resources/` with `#to-read` tags
* `append_to_file` injects reading tasks into project files for automatic cross-linking

### 7. Configuration (`config.py`)
Single source of truth for env vars, paths, model names, and thresholds.

### 8. Daily Briefing (`briefing.py`)
* Scans `~/vault/Inbox/` for files modified in the last 24 hours.
* Synthesizes a daily agenda using Gemini Pro.
* Prioritizes tasks under `## Next Actions`.

### 9. Sync Engine (sync.sh)
* (To be configured post-deployment)

### 10. Task Scheduler (`modules/task_scheduler.py`)
* Bankruptcy protocol for `#to-read` items in `3-Resources/`
* `scan_stale_readings()` detects items older than 90 days (configurable via `READING_STALE_DAYS`)
* `/prune` slash command triggers scan and prompts user
* `/archive_reading` moves stale items to `4-Archives/reading/`
* `/keep` resets frontmatter date to today, retaining items for another cycle