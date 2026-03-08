# Headless Second Brain

An AI-powered local processing agent that receives unstructured text and voice data via Telegram, formats it rigidly using LLMs, and deposits raw Markdown into a local Obsidian vault.

## Current Architecture
- **Environment:** Designed for any POSIX system (macOS/Debian).
- **Ingestion:** Telegram Bot API (`bot.py`).
- **Processing:** `litellm` and `google.genai` routing to `gemini-3.1-flash-lite-preview` (standard) and `gemini-3.1-pro-preview` (via `/pro`).
- **Storage:** Local filesystem ingestion dropping markdown files into a predefined `VAULT_INBOX_DIR`.

## Local Setup (macOS)

Follow these steps to get the agent running on your local machine.

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
VAULT_INBOX_DIR="/Users/priyankdesai/Documents/Brain/vault/Inbox/"
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

To take this codebase from your local macOS machine and run it continuously on a Debian or Ubuntu server, follow these steps.

### 1. Transfer Files
Clone or rsync the `brain-agent` folder to your Debian server. You do not need to transfer the `venv/` folder as it is OS-specific; you will rebuild it on the server.
```bash
scp -r ~/Documents/Brain/brain-agent user@your-debian-server:~/
```

### 2. Server Setup & Dependencies
Log into your Debian server and install Python and virtual environments if you haven't already:
```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
```

Rebuild the environment:
```bash
cd ~/brain-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Variables
Ensure your `.env` file is present in `~/brain-agent/.env` on the Debian server. Update the `VAULT_INBOX_DIR` to match the exact absolute path where your Obsidian vault will live on the server.
```env
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
GEMINI_API_KEY="your_google_ai_studio_key"
ALLOWED_USER_ID="your_telegram_numeric_id"
VAULT_INBOX_DIR="/target/absolute/path/on/debian/vault/Inbox/"
```

### 4. Background Daemon (Systemd for `bot.py`)
To ensure `bot.py` restarts automatically on server reboots or crashes, create a systemd service.

1. Create a service file:
   ```bash
   sudo nano /etc/systemd/system/brainbot.service
   ```
2. Paste the following configuration (adjust the paths to match your Debian user):
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
3. Enable and start the bot:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable brainbot
   sudo systemctl start brainbot
   ```
   *(You can view logs actively via `sudo journalctl -u brainbot -f`)*

### 5. Daily Agenda Scheduling (Cron for `briefing.py`)
To automate the daily morning summary from the `Inbox/` directory, configure a cron job on the Debian server.

1. Open the crontab editor:
   ```bash
   crontab -e
   ```
2. Add a rule to execute at 7:00 AM daily. It is critical to use the absolute path to your Python virtual environment binary:
   ```bash
   0 7 * * * /home/your_debian_username/brain-agent/venv/bin/python /home/your_debian_username/brain-agent/briefing.py >> /home/your_debian_username/brain-agent/cron.log 2>&1
   ```

### 6. Cloud Sync (Rclone - Optional but Recommended)
If you want the Debian server to push your vault changes back to Google Drive (which you can then sync back down to your macOS or iOS Obsidian apps):
1. Install rclone: `sudo apt install rclone`
2. Run `rclone config` to link your Google Drive.
3. Configure `sync.sh` (or add an additional cron job) to trigger `rclone sync /path/to/vault/ remote_name:Vault/` periodically.

### 7. Future: Gemini CLI Automation
As per the project specification, once deployed on Debian, the Gemini CLI can be utilized for batch file management or complex querying over the entire `~/vault/` directory outside of the regular conversational flow. Install it independently on the server via `npm install -g @google/generative-ai-cli` when ready to build out those administrative scripts.
