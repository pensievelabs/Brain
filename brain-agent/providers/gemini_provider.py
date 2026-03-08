import logging
import litellm

from interfaces.llm import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """
    Gemini/LiteLLM implementation of LLMProvider.

    Each instance is configured with a specific model and optional system prompt.
    Multiple modules can each have their own GeminiProvider with different settings.
    """

    def __init__(self, model: str = "gemini/gemini-2.5-flash", system_prompt: str | None = None):
        self.model = model
        self.system_prompt = system_prompt

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """
        Send a completion request via LiteLLM.

        If this provider was constructed with a system_prompt and the messages
        list doesn't already start with a system message, one is prepended.
        """
        # Prepend system prompt if configured and not already present
        if self.system_prompt and (not messages or messages[0].get("role") != "system"):
            messages = [{"role": "system", "content": self.system_prompt}] + messages

        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        logger.info(f"GeminiProvider calling {self.model} ({len(messages)} messages)")

        response = litellm.completion(**kwargs)
        message = response.choices[0].message

        return LLMResponse(
            content=message.content,
            tool_calls=message.tool_calls or [],
            raw=response,
        )
