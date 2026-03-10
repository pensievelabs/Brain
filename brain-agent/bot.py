"""
BrainBot — Thin Entrypoint

Wires together the modular components and starts the Telegram transport.
All logic lives in orchestrator/, providers/, memory/, vault/, and transports/.
"""

import asyncio
import nest_asyncio

from config import Config
from memory.chroma_memory import ChromaMemory
from providers.gemini_provider import GeminiProvider
from vault.vault_tools import VaultManager
from orchestrator.orchestrator import Orchestrator
from transports.telegram_transport import TelegramTransport
from transports.slack_transport import SlackTransport
from interfaces.messaging import MessagingTransport
from utils.logger import get_logger

# Allow nested event loops (needed by some underlying libraries)
nest_asyncio.apply()

# --- Logging ---
logger = get_logger(__name__)


async def main():
    # 1. Load config
    config = Config()

    # 2. Initialize components
    memory = ChromaMemory(config)
    vault = VaultManager(config, memory)

    default_llm = GeminiProvider(model=config.DEFAULT_MODEL)
    pro_llm = GeminiProvider(model=config.PRO_MODEL)

    orchestrator = Orchestrator(
        config=config,
        default_llm=default_llm,
        pro_llm=pro_llm,
        memory=memory,
        vault=vault,
    )

    # 3. Index vault on startup
    asyncio.create_task(memory.index_all(config.VAULT_DIR))

    # 4. Start transports
    transports: list[MessagingTransport] = []
    
    if config.TELEGRAM_BOT_TOKEN:
        telegram_transport = TelegramTransport(config)
        await telegram_transport.start(on_message=orchestrator.handle_message)
        transports.append(telegram_transport)

    if config.SLACK_BOT_TOKEN and config.SLACK_APP_TOKEN:
        slack_transport = SlackTransport(config)
        await slack_transport.start(on_message=orchestrator.handle_message)
        transports.append(slack_transport)

    if not transports:
        logger.warning("No messaging transports started. The bot will run but cannot receive messages.")

    logger.info("BrainBot is running. Press Ctrl+C to stop.")

    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
        for transport in transports:
            await transport.stop()


if __name__ == "__main__":
    asyncio.run(main())
