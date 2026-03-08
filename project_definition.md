# Project: Headless Second Brain (macOS/Debian + Telegram + local Obsidian)

## System Overview
A headless AI agent currently developed on macOS, targeting Debian deployment. Acts as an autonomous Chief of Staff that receives text via Telegram, classifies semantic intent, and manages an Obsidian vault using the PARA method. Features a Propose → Confirm → Act protocol for vault mutations, semantic search via ChromaDB, and specialized `/coach` and `/explore` modes.

## Directory Structure
The project lives in `~/brain-agent/`. The vault lives in `~/vault/`.

~/brain-agent/
├── bot.py                # Main Telegram bot with semantic intent + function calling
├── briefing.py           # Daily cron script for morning summaries
├── agent.md              # System prompt: intent classification, PARA rules, anti-patterns
├── requirements.txt      # Python dependencies
├── chroma_db/            # ChromaDB persistent vector store
└── sync.sh               # Shell script for backup syncs

~/vault/
├── 1-Projects/           # Active projects (#project)
├── 2-Areas/              # Ongoing responsibilities (#area)
├── 3-Resources/          # Interests, research, shower thoughts (#resource)
├── 4-Archives/           # Completed/inactive items (#archive)
├── Inbox/                # Default drop zone for unclassified items
└── Instructions.md       # Vault meta-documentation

## Component Specifications

### 1. Telegram Bot (bot.py)
* Uses `python-telegram-bot` and `litellm` with function calling.
* **Semantic Intent Classification:** Classifies messages as `shower_thought`, `project_creation`, `project_update`, `area_update`, `action_item`, `archival`, `query`, or `correction`.
* **Propose → Confirm → Act Protocol:** For vault-mutating actions, proposes the action first and waits for user confirmation. Queries bypass confirmation.
* **Semantic Search:** ChromaDB with `gemini-embedding-001` embeddings. Injects file content snippets (not just paths) into the LLM prompt.
* **Tools:**
    * `read_vault_file` — Read file content from vault.
    * `overwrite_vault_file` — Create or update files with auto-index update.
    * `list_vault_files` — Browse PARA directory listings.
    * `move_vault_file` — Move files between directories (tag evolution).
* **Multi-turn tool loop:** Up to 5 sequential tool-call rounds per message for search → read → decide → write chains.
* Maintains a Short-Term Rolling Memory buffer (sliding window of 6 messages/3 turns).
* Hardcoded security: only processes messages from `ALLOWED_USER_ID`.
* Models: `gemini-2.5-flash` (default), `gemini-2.5-pro` (coach/explore).
* Follows the **PARA Method** and **Tag Evolution Rules**.

### 2. Daily Briefing (briefing.py)
* Scans `~/vault/Inbox/` for files modified in the last 24 hours.
* Synthesizes a daily agenda using `gemini-2.5-pro`.
* Prioritizes tasks under `## Next Actions`.

### 3. Sync Engine (sync.sh)
* (To be configured post-deployment)