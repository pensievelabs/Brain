"""
BrainBot — Thin Entrypoint

Wires together the modular components and starts the Telegram transport.
All logic lives in orchestrator/, providers/, memory/, vault/, and transports/.
"""

import asyncio
import logging
import nest_asyncio

from config import Config
from memory.chroma_memory import ChromaMemory
from providers.gemini_provider import GeminiProvider
from vault.vault_tools import VaultManager
from orchestrator.orchestrator import Orchestrator
from transports.telegram_transport import TelegramTransport

# Allow nested event loops (needed by some underlying libraries)
nest_asyncio.apply()

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


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

    # 4. Start transport
    transport = TelegramTransport(config)
    await transport.start(on_message=orchestrator.handle_message)

    logger.info("BrainBot is running. Press Ctrl+C to stop.")

    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
        await transport.stop()


if __name__ == "__main__":
    asyncio.run(main())
