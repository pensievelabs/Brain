from typing import Callable, Awaitable
import asyncio

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler

from interfaces.messaging import MessagingTransport
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class SlackTransport(MessagingTransport):
    """
    Slack implementation of MessagingTransport.

    Uses slack_bolt with Socket Mode.
    Handles listening to messages in channels where the bot is invited,
    extracting text, and delegating to the orchestrator.
    """

    def __init__(self, config: Config):
        self.config = config
        self._app: AsyncApp | None = None
        self._handler: AsyncSocketModeHandler | None = None
        self._on_message: Callable[[str, str], Awaitable[str]] | None = None

    async def start(self, on_message: Callable[[str, str], Awaitable[str]]) -> None:
        """Start Slack Socket Mode polling. Does not block the main event loop."""
        if not self.config.SLACK_BOT_TOKEN or not self.config.SLACK_APP_TOKEN:
            logger.error("Missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN.")
            return

        self._on_message = on_message

        # Initialize the AsyncApp
        self._app = AsyncApp(token=self.config.SLACK_BOT_TOKEN)

        # Register message handler for any message events
        @self._app.message(".*")
        async def handle_message_events(message, say, context):
            user_id = message.get("user")
            
            # Optional: Add user ID filtering based on ALLOWED_USER_ID if applicable for Slack
            # In Slack, you might want to allow any user in the workspace or specifically filter.
            # Assuming SLACK_ALLOWED_USER_ID could be configured or using ALLOWED_USER_ID if it's the same.
            
            # Ignore messages from bots (including ourselves)
            if message.get("bot_id"):
                return

            text = message.get("text", "")
            if not text:
                return

            # Strip out bot mention if it exists at the start of the message
            # e.g., "<@U08BERVNFFE> What do I have..." -> " What do I have..."
            bot_user_id = context.get("bot_user_id")
            if bot_user_id:
                mention = f"<@{bot_user_id}>"
                if text.startswith(mention):
                    text = text[len(mention):].strip()

            # Note: you might want to handle thread_ts for threaded conversations
            thread_ts = message.get("thread_ts") or message.get("ts")

            if self._on_message:
                try:
                    logger.info(f"📩 [Slack] Received message from user {user_id}")
                    # Await the response from the orchestrator
                    response = await self._on_message(str(user_id), text)
                    if response:
                        logger.info(f"📤 [Slack] Sending reply ({len(response)} chars)")
                        # Reply in the thread
                        await say(text=response, thread_ts=thread_ts)
                    else:
                        await say(text="Executed.", thread_ts=thread_ts)
                except Exception as e:
                    logger.error(f"Error in Slack message handler: {e}")
                    await say(text="Execution error.", thread_ts=thread_ts)

        self._handler = AsyncSocketModeHandler(self._app, self.config.SLACK_APP_TOKEN)
        
        logger.info("SlackTransport starting Socket Mode connection...")
        
        # Start connecting in the background
        asyncio.create_task(self._handler.start_async())

    async def send(self, chat_id: str, text: str) -> None:
        """Send a message to a specific Slack user or channel."""
        if self._app:
            try:
                await self._app.client.chat_postMessage(
                    channel=chat_id,
                    text=text
                )
            except Exception as e:
                logger.error(f"Error sending message to Slack channel {chat_id}: {e}")

    async def stop(self) -> None:
        """Gracefully shut down Slack Socket Mode connection."""
        if self._handler:
            # Depending on slack_bolt version, you might need to close the client manually
            if hasattr(self._handler, "close_async"):
                await self._handler.close_async()
            elif hasattr(self._handler, "disconnect_async"):
                await self._handler.disconnect_async()
            logger.info("SlackTransport stopped.")
