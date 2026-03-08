# Headless Second Brain

An AI-powered local processing agent that receives unstructured text via Telegram, classifies semantic intent, and deposits structured Markdown into a local Obsidian vault using the PARA method.

## Architecture

The codebase uses a **modular, interface-driven** design. Each concern (messaging, LLM, memory, vault) is defined by an ABC and can be swapped independently. See [BotDesign.md](BotDesign.md) for the full architecture reference.

```
brain-agent/
├── bot.py                       # Thin entrypoint — wires components and starts
├── config.py                    # Centralized env vars, paths, model names
├── agent.md                     # Master orchestrator prompt
├── BotDesign.md                 # Architecture design reference
│
├── interfaces/                  # ABCs (contracts)
│   ├── messaging.py             # MessagingTransport
│   ├── llm.py                   # LLMProvider + LLMResponse
│   └── memory.py                # MemoryBackend + SearchResult
│
├── transports/                  # Messaging implementations
│   └── telegram_transport.py    # Telegram via python-telegram-bot
│
├── providers/                   # LLM implementations
│   └── gemini_provider.py       # Gemini via LiteLLM
│
├── memory/                      # Vector memory implementations
│   └── chroma_memory.py         # ChromaDB + gemini-embedding-001
│
├── vault/                       # Vault file operations + tool schemas
│   └── vault_tools.py           # VaultManager class
│
├── orchestrator/                # Central routing and workflow engine
│   └── orchestrator.py          # Orchestrator class
│
├── modules/                     # Future capability modules (coach, calendar, etc.)
│
├── prompts/                     # Per-module system prompts (.md)
│   ├── classifier.md
│   ├── coach.md
│   └── explore.md
│
├── briefing.py                  # Daily cron script for morning summaries
├── chroma_db/                   # ChromaDB persistent vector store
└── requirements.txt
```

**Key components:**
- **Orchestrator** — Central brain: semantic search → prompt build → LLM call → tool dispatch → response. Transport-agnostic.
- **TelegramTransport** — Handles Telegram polling, auth, message extraction. Swappable for Slack, CLI, Discord.
- **GeminiProvider** — Wraps LiteLLM. Each module can have its own instance with a different model and prompt.
- **ChromaMemory** — ChromaDB with `gemini-embedding-001`. Dual task types (RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY).
- **VaultManager** — Secure file ops + tool schemas for LLM function calling. Auto-indexes on mutations.

**Model routing** (configurable via env vars or `config.py`):
- `DEFAULT_MODEL` → `gemini/gemini-2.5-flash` (standard messages)
- `PRO_MODEL` → `gemini/gemini-2.5-pro` (coach/explore modes)

## How It Works

### Semantic Intent Classification
Every incoming message is classified into one of these intents:

| Intent | What it does |
|---|---|
| `shower_thought` | Files to `3-Resources/` |
| `project_creation` | Creates in `1-Projects/` with template |
| `project_update` | Appends to existing project file |
| `area_update` | Files to `2-Areas/` |
| `action_item` | Appends `- [ ]` to related file or `Inbox/` |
| `archival` | Moves to `4-Archives/` |
| `query` | Replies with content, no file mutation |
| `correction` | Re-proposes previous action with changes |

### Propose → Confirm → Act
For vault-mutating actions, the bot:
1. Classifies intent and searches for related files
2. Proposes the action (file, location, content summary)
3. Waits for user confirmation or correction
4. Executes only after "yes"

Queries and `/coach`/`/explore` skip confirmation.

### Available Tools
- `read_vault_file` — Read file content
- `overwrite_vault_file` — Create or update files
- `list_vault_files` — Browse PARA directories
- `move_vault_file` — Move files between directories (tag evolution)

## Local Setup (macOS)

### 1. Project Initialization
```bash
cd ~/Documents/Brain/brain-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration
Create a `.env` file in the `brain-agent` directory:
```env
TELEGRAM_BOT_TOKEN="your_token"
GEMINI_API_KEY="your_key"
ALLOWED_USER_ID="your_id"

# Optional model overrides:
# DEFAULT_MODEL="gemini/gemini-2.5-flash"
# PRO_MODEL="gemini/gemini-2.5-pro"
```

### 3. Usage
Run the bot:
```bash
python bot.py
```
Run the daily briefing manually:
```bash
python briefing.py
```

---

## Debian / Ubuntu Deployment Guide

### 1. Transfer Files
```bash
scp -r ~/Documents/Brain/brain-agent user@your-debian-server:~/
```

### 2. Server Setup & Dependencies
Requires Python 3.11+. Dependencies are pinned in `requirements.txt` for reproducibility.
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
cd ~/brain-agent
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Variables
Create `~/brain-agent/.env` on the server.
```env
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
GEMINI_API_KEY="your_google_ai_studio_key"
ALLOWED_USER_ID="your_telegram_numeric_id"
```

### 4. Background Daemon (Systemd)
```bash
sudo nano /etc/systemd/system/brainbot.service
```
```ini
[Unit]
Description=BrainBot Telegram Listener
After=network.target

[Service]
User=your_debian_username
WorkingDirectory=/home/your_debian_username/brain-agent
ExecStart=/home/your_debian_username/brain-agent/venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable brainbot
sudo systemctl start brainbot
```

### 5. Daily Agenda (Cron)
```bash
crontab -e
# Add:
0 7 * * * /home/your_debian_username/brain-agent/venv/bin/python /home/your_debian_username/brain-agent/briefing.py >> /home/your_debian_username/brain-agent/cron.log 2>&1
```

### 6. Cloud Sync (Rclone - Optional)
```bash
sudo apt install rclone
rclone config
# Then schedule: rclone sync /path/to/vault/ remote_name:Vault/
```
