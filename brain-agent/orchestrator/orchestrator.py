import os
import json
import asyncio
from datetime import date

from interfaces.llm import LLMProvider
from interfaces.memory import MemoryBackend
from vault.vault_tools import VaultManager
from modules.task_scheduler import scan_stale_readings, format_bankruptcy_message, update_frontmatter_date
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class Orchestrator:
    """
    Central brain that routes messages, chains tools, and coordinates workflows.

    This is transport-agnostic: it receives (user_id, text) and returns a response string.
    The transport layer handles delivery.

    Responsibilities:
        1. Semantic search for vault context
        2. System prompt construction (agent.md + search results + date)
        3. LLM calls with tool dispatch (multi-turn, up to MAX_TOOL_ROUNDS)
        4. Rolling chat history management (6-message window)
        5. Model routing (flash for default, pro for /coach and /explore)
    """

    def __init__(
        self,
        config: Config,
        default_llm: LLMProvider,
        pro_llm: LLMProvider,
        memory: MemoryBackend,
        vault: VaultManager,
    ):
        self.config = config
        self.default_llm = default_llm
        self.pro_llm = pro_llm
        self.memory = memory
        self.vault = vault

        self._tools = vault.get_tool_schemas() + vault.get_reading_tool_schemas()
        self._tool_fns = vault.get_tool_functions()

        # Per-user rolling chat history: { user_id: [messages] }
        self._chat_history: dict[str, list[dict]] = {}

    async def handle_message(self, user_id: str, text: str) -> str:
        """
        Process a user message end-to-end and return the response.

        This is the single entry point called by any MessagingTransport.
        """
        # 1. Route to the right LLM
        llm = self._select_llm(text)
        logger.info(f"\n{'='*60}")
        logger.info(f"📨 [Orchestrator] New message from user {user_id}")
        logger.info(f"📝 [Orchestrator] Text: {text[:100]}{'...' if len(text) > 100 else ''}")
        logger.info(f"🤖 [Orchestrator] Routed to LLM: {llm.model}")

        # Handle reading-queue slash commands (bypass LLM)
        if text.strip() == "/prune":
            return await self._handle_prune()
        if text.strip() == "/archive_reading":
            return await self._handle_archive_reading()
        if text.strip() == "/keep":
            return await self._handle_keep()

        # 2. Semantic search (offload to thread — ChromaDB is sync)
        logger.info("🔍 [Memory] Running semantic search...")
        search_results = await asyncio.to_thread(self.memory.search, text)
        if search_results:
            logger.info(f"🔍 [Memory] Found {len(search_results)} relevant file(s):")
            for r in search_results:
                rel = os.path.relpath(r.doc_id, self.config.VAULT_DIR) if r.doc_id.startswith(self.config.VAULT_DIR) else r.doc_id
                logger.info(f"   📎 {rel} (distance: {r.distance:.4f})")
        else:
            logger.info("🔍 [Memory] No relevant files found.")

        # 3. Update rolling history
        history = self._chat_history.setdefault(user_id, [])
        history.append({"role": "user", "content": text})
        if len(history) > 6:
            self._chat_history[user_id] = history[-6:]
            history = self._chat_history[user_id]

        # 4. Build system prompt
        system_prompt = self._build_system_prompt(search_results)
        messages = [{"role": "system", "content": system_prompt}] + history

        # 5. Initial LLM call
        logger.info(f"🧠 [LLM] Calling {llm.model} with {len(messages)} messages...")
        try:
            response = await asyncio.to_thread(llm.complete, messages, self._tools)

            if response.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in response.tool_calls
                    ],
                })
                final_content, modified_files = await self._execute_tool_calls(
                    response.tool_calls, messages, llm
                )
            else:
                final_content = response.content
                modified_files = []

        except Exception as e:
            logger.error(f"LLM or tool execution error: {e}")
            return "Execution error."

        # 6. Update history with assistant response
        if final_content:
            history.append({"role": "assistant", "content": final_content})

        # 7. Format reply
        if modified_files:
            logger.info(f"📁 [Vault] Modified {len(modified_files)} file(s): {', '.join(os.path.basename(f) for f in modified_files)}")
            if not final_content:
                file_list = ", ".join(os.path.basename(f) for f in modified_files)
                logger.info(f"{'='*60}")
                return f"📁 Done → {file_list}"

        logger.info(f"✅ [Orchestrator] Response ready ({len(final_content or '')} chars)")
        logger.info(f"{'='*60}")
        return final_content or "Executed."

    def _select_llm(self, text: str) -> LLMProvider:
        """Route to pro model for /coach and /explore, default otherwise."""
        if text.startswith("/coach") or text.startswith("/explore"):
            return self.pro_llm
        return self.default_llm

    def _build_system_prompt(self, search_results: list) -> str:
        """Build the full system prompt with agent rules and semantic context."""
        system_prompt = "You are BrainBot."
        try:
            if os.path.exists(self.config.AGENT_MD_PATH):
                with open(self.config.AGENT_MD_PATH, "r", encoding="utf-8") as f:
                    system_prompt = f.read()
        except Exception as e:
            logger.error(f"Could not read agent.md: {e}")

        # Inject search results as content
        if search_results:
            context_parts = ["## Vault Context (from semantic search)\n"]
            for result in search_results:
                rel_path = (
                    os.path.relpath(result.doc_id, self.config.VAULT_DIR)
                    if result.doc_id.startswith(self.config.VAULT_DIR)
                    else result.doc_id
                )
                context_parts.append(f"### File: `{rel_path}`\n```\n{result.snippet}\n```\n")
            context_str = "\n".join(context_parts)
            # Query response instructions
            context_str += (
                "\n## Query Response Instructions\n"
                "When answering a query, follow these rules strictly:\n"
                "1. Cite every vault file you reference using `📎 Source: [relative path]`.\n"
                "2. If you add information from your own training data beyond what the vault contains, "
                "put it under a `📚 Additional Context (not from your vault)` header. Never blend it silently.\n"
                "3. Exclude unvetted sources (Grokipedia, unmoderated wikis). Only cite authoritative, expert sources.\n"
                "4. Lead with vault content. Only supplement if the vault is incomplete or the user asks for more.\n"
            )
        else:
            context_str = "## Vault Context\nNo existing relevant files found in the vault."

        today = date.today().isoformat()
        return f"{system_prompt}\n\n---\n**Today's date:** {today}\n**Vault root:** `{self.config.VAULT_DIR}`\n\n{context_str}"

    async def _execute_tool_calls(self, tool_calls, messages: list, llm: LLMProvider):
        """
        Execute tool calls in a multi-turn loop (up to MAX_TOOL_ROUNDS).

        Returns (final_content, modified_files).
        """
        modified_files = []

        for round_num in range(self.config.MAX_TOOL_ROUNDS):
            if not tool_calls:
                break

            logger.info(f"🔧 [Tools] Round {round_num + 1}: {len(tool_calls)} call(s)")

            for tc in tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                logger.info(f"   🔧 [Vault] {fn_name}({json.dumps(fn_args)[:200]})")

                handler = self._tool_fns.get(fn_name)
                if handler:
                    result = await asyncio.to_thread(handler, fn_args)
                    if fn_name == "overwrite_vault_file":
                        modified_files.append(fn_args.get("filepath", ""))
                    elif fn_name == "move_vault_file":
                        modified_files.append(fn_args.get("destination_filepath", ""))
                    elif fn_name == "append_to_file":
                        modified_files.append(fn_args.get("filepath", ""))
                    elif fn_name == "create_reading_stub":
                        modified_files.append(fn_args.get("title", "reading-stub"))
                else:
                    result = f"Unknown function: {fn_name}"

                messages.append({
                    "tool_call_id": tc.id,
                    "role": "tool",
                    "name": fn_name,
                    "content": str(result),
                })

            # Ask the LLM to continue
            logger.info(f"🧠 [LLM] Continue call ({llm.model})...")
            next_resp = await asyncio.to_thread(llm.complete, messages, self._tools)

            if next_resp.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": next_resp.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in next_resp.tool_calls
                    ],
                })
                tool_calls = next_resp.tool_calls
            else:
                return next_resp.content, modified_files

        # Exhausted rounds — final call without tools
        final_resp = await asyncio.to_thread(llm.complete, messages)
        return final_resp.content, modified_files

    # --- Reading Queue Slash Commands ---

    async def _handle_prune(self) -> str:
        """Scan for stale #to-read items and return a formatted report."""
        logger.info("📚 [Orchestrator] Running /prune scan...")
        stale_items = await asyncio.to_thread(
            scan_stale_readings,
            self.config.VAULT_DIR,
            self.config.READING_STALE_DAYS,
        )
        msg = format_bankruptcy_message(stale_items)
        logger.info(f"📚 [Orchestrator] /prune found {len(stale_items)} stale item(s)")
        return msg

    async def _handle_archive_reading(self) -> str:
        """Move all stale #to-read items to 4-Archives/reading/."""
        logger.info("📚 [Orchestrator] Running /archive_reading...")
        stale_items = await asyncio.to_thread(
            scan_stale_readings,
            self.config.VAULT_DIR,
            self.config.READING_STALE_DAYS,
        )
        if not stale_items:
            return "✅ No stale reading items to archive."

        archived = []
        for item in stale_items:
            src = item["filepath"]
            basename = os.path.basename(src)
            dst = f"4-Archives/reading/{basename}"
            result = await asyncio.to_thread(self.vault.move_file, src, dst)
            archived.append(f"  • `{src}` → `{dst}`")
            logger.info(f"📁 [Vault] {result}")

        return f"📁 Archived {len(archived)} item(s):\n" + "\n".join(archived)

    async def _handle_keep(self) -> str:
        """Reset the date on all stale #to-read items to today."""
        logger.info("📚 [Orchestrator] Running /keep...")
        stale_items = await asyncio.to_thread(
            scan_stale_readings,
            self.config.VAULT_DIR,
            self.config.READING_STALE_DAYS,
        )
        if not stale_items:
            return "✅ No stale reading items to retain."

        kept = []
        for item in stale_items:
            filepath = os.path.join(self.config.VAULT_DIR, item["filepath"])
            result = await asyncio.to_thread(update_frontmatter_date, filepath)
            kept.append(f"  • `{item['filepath']}` — date reset to today")
            logger.info(f"📅 [Scheduler] {result}")

        return f"📅 Retained {len(kept)} item(s) (date reset to today):\n" + "\n".join(kept)
