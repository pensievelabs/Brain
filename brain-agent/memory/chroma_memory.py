import os
import glob
import logging

import chromadb
from chromadb.utils.embedding_functions import GoogleGenerativeAiEmbeddingFunction

from interfaces.memory import MemoryBackend, SearchResult
from config import Config

logger = logging.getLogger(__name__)


class ChromaMemory(MemoryBackend):
    """
    ChromaDB implementation of MemoryBackend.

    Uses gemini-embedding-001 with separate task types for documents vs queries
    to get better retrieval quality.
    """

    def __init__(self, config: Config):
        self.config = config

        self._client = chromadb.PersistentClient(path=config.CHROMA_DB_DIR)

        self._embed_doc = GoogleGenerativeAiEmbeddingFunction(
            api_key=config.GEMINI_API_KEY,
            task_type="RETRIEVAL_DOCUMENT",
            model_name="models/gemini-embedding-001",
        )
        self._embed_query = GoogleGenerativeAiEmbeddingFunction(
            api_key=config.GEMINI_API_KEY,
            task_type="RETRIEVAL_QUERY",
            model_name="models/gemini-embedding-001",
        )

        self._collection = self._client.get_or_create_collection(
            name="vault_notes",
            embedding_function=self._embed_doc,
        )

    async def index_all(self, directory: str) -> None:
        """Scan directory for .md files and upsert all into ChromaDB."""
        logger.info(f"Starting full index of {directory}...")
        files = glob.glob(os.path.join(directory, "**", "*.md"), recursive=True)

        for filepath in files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                self._collection.upsert(
                    documents=[content],
                    metadatas=[{"filepath": filepath}],
                    ids=[filepath],
                )
            except Exception as e:
                logger.error(f"Error indexing {filepath}: {e}")

        logger.info(f"Finished indexing {len(files)} files.")

    def upsert(self, doc_id: str, content: str, metadata: dict | None = None) -> None:
        """Insert or update a single document in the index."""
        try:
            meta = metadata or {}
            if "filepath" not in meta:
                meta["filepath"] = doc_id
            self._collection.upsert(
                documents=[content],
                metadatas=[meta],
                ids=[doc_id],
            )
            logger.info(f"Upserted index for {doc_id}")
        except Exception as e:
            logger.error(f"Error upserting index for {doc_id}: {e}")

    def remove(self, doc_id: str) -> None:
        """Remove a document from the index."""
        try:
            self._collection.delete(ids=[doc_id])
            logger.info(f"Removed index for {doc_id}")
        except Exception as e:
            logger.error(f"Error removing index for {doc_id}: {e}")

    def search(self, query: str, n_results: int = 5) -> list[SearchResult]:
        """
        Semantic search using query-optimized embeddings.

        Filters out results above the similarity threshold.
        """
        try:
            query_embeddings = self._embed_query([query])

            results = self._collection.query(
                query_embeddings=query_embeddings,
                n_results=n_results,
                include=["documents", "distances", "metadatas"],
            )

            if not results or not results.get("distances") or not results["distances"][0]:
                return []

            distances = results["distances"][0]
            documents = results["documents"][0]
            ids = results["ids"][0]

            matched = []
            max_chars = self.config.MAX_SNIPPET_CHARS
            threshold = self.config.SIMILARITY_THRESHOLD

            for dist, doc, file_id in zip(distances, documents, ids):
                if dist <= threshold:
                    snippet = doc[:max_chars] + ("..." if len(doc) > max_chars else "")
                    matched.append(SearchResult(doc_id=file_id, snippet=snippet, distance=dist))
                    logger.info(f"Semantic match: {file_id} (distance: {dist:.4f})")
                else:
                    logger.info(f"Skipped: {file_id} (distance: {dist:.4f}, above threshold)")

            return matched

        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []
