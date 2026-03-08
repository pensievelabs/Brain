import os
import datetime
import litellm
from telegram import Bot
import asyncio
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
VAULT_DIR = os.getenv("VAULT_INBOX_DIR", os.path.expanduser("/Users/priyankdesai/Documents/Brain/vault/Inbox/"))

async def main():
    if not TOKEN or not ALLOWED_USER_ID:
        print("Missing credentials (TELEGRAM_BOT_TOKEN or ALLOWED_USER_ID).")
        return

    # Scan for files modified in last 24h
    now = datetime.datetime.now()
    recent_texts = []
    
    if os.path.exists(VAULT_DIR):
        for filename in os.listdir(VAULT_DIR):
            if not filename.endswith(".md"): continue
            
            filepath = os.path.join(VAULT_DIR, filename)
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(filepath))
            
            if now - mtime <= datetime.timedelta(hours=24):
                with open(filepath, "r") as f:
                    recent_texts.append(f"--- File: {filename} ---\n{f.read()}")

    if not recent_texts:
        print("No recent files modified in the last 24 hours.")
        return

    combined_text = "\n\n".join(recent_texts)
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Synthesize the provided notes from the last 24 hours into a cohesive daily agenda. Prioritize any tasks under a '## Next Actions' header at the bottom of the response. Output your response as a clear, readable message for Telegram."},
        {"role": "user", "content": combined_text}
    ]
    
    try:
        response = litellm.completion(
            model="gemini/gemini-3.1-pro-preview",
            messages=messages
        )
        
        briefing = response.choices[0].message.content
        
        bot = Bot(token=TOKEN)
        await bot.send_message(chat_id=ALLOWED_USER_ID, text=briefing)
        print("Briefing sent successfully.")
    except Exception as e:
        print(f"Error generating or sending briefing: {e}")

if __name__ == "__main__":
    asyncio.run(main())
