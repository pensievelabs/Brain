# BrainBot — Modular Architecture Design

> Reference document for the pluggable, interface-driven architecture of BrainBot.
> Created: 2026-03-08

---

## Design Principles

1. **Interface-driven**: Every major concern (messaging, LLM, memory) is defined by an ABC. Swap implementations without touching business logic.
2. **Module-per-capability**: Each future feature (coach, calendar, journal, task scheduler) lives in its own module with its own prompt and LLM config.
3. **Orchestrator pattern**: A central brain routes messages, chains tools, and coordinates multi-step workflows across modules.
4. **Prompt-as-config**: System prompts live in `.md` files, not Python strings. Edit behavior without touching code.

---

## Directory Structure

```
brain-agent/
├── bot.py                       # Thin entrypoint — wires components and starts
├── config.py                    # Centralized env vars and paths
├── agent.md                     # Master orchestrator prompt
├── BotDesign.md                 # This file
│
├── interfaces/                  # ABCs (contracts)
│   ├── messaging.py             # MessagingTransport
│   ├── llm.py                   # LLMProvider
│   └── memory.py                # MemoryBackend
│
├── transports/                  # Messaging implementations
│   └── telegram_transport.py    # Telegram via python-telegram-bot
│
├── providers/                   # LLM implementations
│   └── gemini_provider.py       # Gemini via LiteLLM
│
├── memory/                      # Vector memory implementations
│   └── chroma_memory.py         # ChromaDB + gemini-embedding-001
│
├── vault/                       # Vault file operations + tool schemas
│   └── vault_tools.py           # VaultManager class
│
├── orchestrator/                # Central routing and workflow engine
│   └── orchestrator.py          # Orchestrator class
│
├── utils/                       # Shared utilities
│   └── logger.py                # Centralized daily logging
│
├── modules/                     # Future capability modules
│   └── (coach, calendar, journal, task_scheduler, ...)
│
├── prompts/                     # Per-module system prompts (.md)
│   ├── classifier.md
│   ├── coach.md
│   └── explore.md
│
├── briefing.py                  # Standalone daily briefing (to be refactored later)
├── chroma_db/                   # Persistent vector store data
└── requirements.txt
```

---

## Interfaces

### MessagingTransport
```python
class MessagingTransport(ABC):
    async def start(self, on_message: Callable) -> None
    async def send(self, chat_id: str, text: str) -> None
    async def stop(self) -> None
```
The `on_message` callback signature: `async def handler(user_id: str, text: str) -> str`

### LLMProvider
```python
class LLMProvider(ABC):
    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse

@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list | None
```
Each module instantiates its own provider with a specific model + system prompt.

### MemoryBackend
```python
class MemoryBackend(ABC):
    async def index_all(self, directory: str) -> None
    def upsert(self, doc_id: str, content: str, metadata: dict) -> None
    def remove(self, doc_id: str) -> None
    def search(self, query: str, n_results: int = 5) -> list[SearchResult]

@dataclass
class SearchResult:
    doc_id: str
    snippet: str
    distance: float
```

---

## Data Flow

```
User Message (Telegram/Slack/CLI)
        │
        ▼
 MessagingTransport
        │  on_message(user_id, text) -> str
        ▼
   Orchestrator
        │
        ├── MemoryBackend.search(text)       → vault context
        ├── build_system_prompt(context)      → agent.md + search results
        ├── LLMProvider.complete(messages)    → intent + response/tool_calls
        ├── VaultManager.execute(tool_calls)  → file mutations
        │       └── MemoryBackend.upsert()    → auto-reindex
        └── (future) dispatch to sub-modules  → coach, calendar, etc.
        │
        ▼
  Final response string
        │
        ▼
 MessagingTransport.send()
```

---

## Module Pattern (Future)

Each new capability follows this pattern:

```python
class CoachModule:
    def __init__(self, llm: LLMProvider, memory: MemoryBackend, vault: VaultManager):
        self.llm = GeminiProvider(model="gemini/gemini-2.5-pro", 
                                  system_prompt=load("prompts/coach.md"))
        self.memory = memory
        self.vault = vault

    async def run(self, user_text: str, chat_history: list) -> str:
        # Module-specific logic
        ...
```

The Orchestrator detects `/coach`, `/explore`, or future slash commands and delegates to the appropriate module.

---

## Key Configuration (config.py)

| Variable | Source | Default |
|---|---|---|
| `ALLOWED_USER_ID` | env | required |
| `TELEGRAM_BOT_TOKEN` | env | required |
| `GEMINI_API_KEY` | env | required |
| `VAULT_DIR` | env / hardcoded | `~/Documents/Brain/vault` |
| `AGENT_DIR` | env / hardcoded | `~/Documents/Brain/brain-agent` |
| `SIMILARITY_THRESHOLD` | code | `0.75` |
| `MAX_SNIPPET_CHARS` | code | `500` |
| `MAX_TOOL_ROUNDS` | code | `5` |
