from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SearchResult:
    """A single semantic search hit."""
    doc_id: str
    snippet: str
    distance: float


class MemoryBackend(ABC):
    """
    Abstract interface for vector memory / semantic search backends.

    Swappable between ChromaDB, Pinecone, SQLite FTS, etc.
    """

    @abstractmethod
    async def index_all(self, directory: str) -> None:
        """Scan a directory and upsert all .md files into the index."""
        ...

    @abstractmethod
    def upsert(self, doc_id: str, content: str, metadata: dict | None = None) -> None:
        """Insert or update a single document in the index."""
        ...

    @abstractmethod
    def remove(self, doc_id: str) -> None:
        """Remove a document from the index."""
        ...

    @abstractmethod
    def search(self, query: str, n_results: int = 5) -> list[SearchResult]:
        """
        Semantic search for documents matching the query.

        Returns results filtered by the configured similarity threshold.
        """
        ...

    @abstractmethod
    def search_by_tag(self, query: str, tag: str, n_results: int = 5) -> list[SearchResult]:
        """
        Semantic search restricted to documents containing a specific tag.

        Used to find e.g. only #project notes when linking reading materials.
        """
        ...
