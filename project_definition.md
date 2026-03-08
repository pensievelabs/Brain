# Project: Headless Second Brain (macOS/Debian + Telegram + local Obsidian)

## System Overview
A headless AI agent currently being developed and run on macOS, with the target deployment being a Debian server. It acts as an autonomous Chief of Staff, receiving text and audio via Telegram, processing them using LiteLLM with function calling capabilities. It can search the vault, integrate new information, and evolve PARA tags dynamically. It supports `/coach` and `/explore` specialized modes.

## Directory Structure
The project lives in `~/brain-agent/`. The vault lives in `~/vault/`.

~/brain-agent/
├── bot.py                # Main Telegram bot listener with function calling
├── briefing.py           # Daily cron script for morning summaries
├── agent.md              # The system prompt with PARA and autonomous rules
├── requirements.txt      # Python dependencies
└── sync.sh               # Shell script for backup syncs

~/vault/
├── 1-Projects/           # Active projects
├── 2-Areas/              # Responsibilities
├── 3-Resources/          # Interests and saved content
├── 4-Archives/           # Completed items
└── Inbox/                # Default drop zone for bot.py

## Component Specifications

### 1. Telegram Bot (bot.py)
* Uses `python-telegram-bot` and `litellm` with function calling.
* Maintains a Short-Term Rolling Memory buffer (sliding window of 6 messages/3 turns) using `context.user_data` to support multi-turn conversations without token bloat.
* Implements `read_vault_file` and `overwrite_vault_file` tools.
* Hardcoded security check to only allow messages from a specific `USER_ID`.
* Listens for text, audio memos, and specific commands:
    * `/pro`: Upgrades to `gemini-3.1-pro-preview`.
    * `/coach`: Activates uncompromising executive coach mode.
    * `/explore`: Activates algorithmic serendipity engine mode.
* Dynamically injects the current system date (`YYYY-MM-DD`) into the system prompt.
* Follows the **PARA Method** and **Evolution Rules** for file organization.
* Sanitizes the output by stripping markdown wrappers.
* **Debian Deployment Note:** Gemini CLI will be integrated post-migration for additional batch tasks.

### 2. Daily Briefing (briefing.py)
* A script designed to scan `~/vault/Inbox/` for files modified in the last 24 hours.
* Compiles the text and sends it to `gemini-3.1-pro-preview`.
* Asks the model to synthesize a daily agenda and prioritize tasks under `## Next Actions`.

### 3. Sync Engine (sync.sh)
* (To be configured post-deployment)