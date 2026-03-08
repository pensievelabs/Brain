from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str | None = None
    tool_calls: list = field(default_factory=list)
    raw: object = None  # Original provider response for edge cases


class LLMProvider(ABC):
    """
    Abstract interface for LLM providers.

    Each module can instantiate its own LLMProvider with a different
    model and system prompt, decoupling model selection from business logic.
    """

    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """
        Send a completion request to the LLM.

        Args:
            messages: OpenAI-format message list (system, user, assistant, tool).
            tools: Optional list of tool schemas for function calling.
            tool_choice: Tool selection strategy ("auto", "none", "required").

        Returns:
            LLMResponse with content and/or tool_calls.
        """
        ...
