from typing import Callable, Awaitable

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from interfaces.messaging import MessagingTransport
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramTransport(MessagingTransport):
    """
    Telegram implementation of MessagingTransport.

    Wraps python-telegram-bot's Application into the transport interface.
    Handles user authentication, message extraction, and reply delivery.
    """

    def __init__(self, config: Config):
        self.config = config
        self._application: Application | None = None
        self._on_message: Callable[[str, str], Awaitable[str]] | None = None

    async def start(self, on_message: Callable[[str, str], Awaitable[str]]) -> None:
        """Start Telegram polling. Blocks until stopped."""
        if not self.config.TELEGRAM_BOT_TOKEN:
            logger.error("No TELEGRAM_BOT_TOKEN provided.")
            return

        self._on_message = on_message
        self._application = (
            Application.builder()
            .token(self.config.TELEGRAM_BOT_TOKEN)
            .build()
        )
        self._application.add_handler(
            MessageHandler(
                filters.TEXT | filters.AUDIO | filters.VOICE,
                self._handle_update,
            )
        )

        logger.info("TelegramTransport starting polling...")
        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    async def send(self, chat_id: str, text: str) -> None:
        """Send a message to a Telegram chat."""
        if self._application:
            await self._application.bot.send_message(
                chat_id=int(chat_id), text=text
            )

    async def stop(self) -> None:
        """Gracefully shut down Telegram polling."""
        if self._application:
            await self._application.updater.stop()
            await self._application.stop()
            await self._application.shutdown()
            logger.info("TelegramTransport stopped.")

    async def _handle_update(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Internal handler: authenticate, extract text, delegate to orchestrator."""
        user_id = update.effective_user.id
        if self.config.ALLOWED_USER_ID and user_id != self.config.ALLOWED_USER_ID:
            logger.warning(f"Unauthorized access attempt from user {user_id}")
            return

        user_text = update.message.text or update.message.caption
        if not user_text:
            await update.message.reply_text("I can only process text right now.")
            return

        if self._on_message:
            try:
                logger.info(f"📩 [Telegram] Received message from user {user_id}")
                response = await self._on_message(str(user_id), user_text)
                logger.info(f"📤 [Telegram] Sending reply ({len(response or '')} chars)")
                await update.message.reply_text(response or "Executed.")
            except Exception as e:
                logger.error(f"Error in message handler: {e}")
                await update.message.reply_text("Execution error.")
