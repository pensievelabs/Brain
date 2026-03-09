import litellm

from interfaces.llm import LLMProvider, LLMResponse
from utils.logger import get_logger

logger = get_logger(__name__)


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

        logger.info(f"🧠 [LLM] Calling {self.model} with {len(messages)} messages.")
        for i, msg in enumerate(messages):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            # Truncate extremely long system prompts if necessary, but keep user/assistant clear
            if isinstance(content, str) and len(content) > 500 and role == 'system':
                display_content = content[:500] + "... [System Prompt Truncated]"
            else:
                display_content = content
            logger.info(f"   ► Msg {i} [{role.upper()}]: {display_content}")

        response = litellm.completion(**kwargs)
        message = response.choices[0].message

        logger.info(f"🧠 [LLM] Received response from {self.model}:")
        if message.content:
            logger.info(f"   ◄ Content: {message.content}")
        if message.tool_calls:
            logger.info(f"   ◄ Tool Calls: {len(message.tool_calls)}")
            for tc in message.tool_calls:
                logger.info(f"       - {tc.function.name}({tc.function.arguments})")

        return LLMResponse(
            content=message.content,
            tool_calls=message.tool_calls or [],
            raw=response,
        )
