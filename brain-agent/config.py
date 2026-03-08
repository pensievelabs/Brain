import os
import logging

logger = logging.getLogger(__name__)


class Config:
    """Centralized configuration from environment variables and defaults."""

    def __init__(self):
        self.ALLOWED_USER_ID = os.environ.get("ALLOWED_USER_ID")
        if self.ALLOWED_USER_ID:
            self.ALLOWED_USER_ID = int(self.ALLOWED_USER_ID)

        self.TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

        self.VAULT_DIR = os.path.expanduser("~/Documents/Brain/vault")
        self.AGENT_DIR = os.path.expanduser("~/Documents/Brain/brain-agent")
        self.CHROMA_DB_DIR = os.path.join(self.AGENT_DIR, "chroma_db")
        self.AGENT_MD_PATH = os.path.join(self.AGENT_DIR, "agent.md")
        self.PROMPTS_DIR = os.path.join(self.AGENT_DIR, "prompts")

        # Model configuration — change these to swap model tiers
        self.DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "gemini/gemini-2.5-flash")
        self.PRO_MODEL = os.environ.get("PRO_MODEL", "gemini/gemini-2.5-pro")

        # Similarity Threshold — gemini-embedding-001 cosine distances:
        # 0.3-0.5 = strong match, 0.5-0.7 = moderate match, >0.8 = weak/unrelated
        self.SIMILARITY_THRESHOLD = 0.75
        self.MAX_SNIPPET_CHARS = 500
        self.MAX_TOOL_ROUNDS = 5

        self._validate()

    def _validate(self):
        missing = []
        if not self.ALLOWED_USER_ID:
            missing.append("ALLOWED_USER_ID")
        if not self.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")
        if missing:
            logger.error(f"Missing required environment variables: {', '.join(missing)}")

    def load_prompt(self, name: str) -> str:
        """Load a prompt file from the prompts/ directory by name (without extension)."""
        path = os.path.join(self.PROMPTS_DIR, f"{name}.md")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(f"Prompt file not found: {path}")
            return ""
