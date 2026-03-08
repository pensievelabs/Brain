from abc import ABC, abstractmethod
from typing import Callable, Awaitable


class MessagingTransport(ABC):
    """
    Abstract interface for messaging platforms.

    Any transport (Telegram, Slack, CLI, Discord) implements this.
    The rest of the system never touches platform-specific APIs directly.
    """

    @abstractmethod
    async def start(self, on_message: Callable[[str, str], Awaitable[str]]) -> None:
        """
        Start listening for messages.

        Args:
            on_message: Callback with signature (user_id: str, text: str) -> response: str.
                        The transport calls this for every incoming message and sends
                        the returned string back to the user.
        """
        ...

    @abstractmethod
    async def send(self, chat_id: str, text: str) -> None:
        """Send a message to a specific chat/user."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down the transport."""
        ...
