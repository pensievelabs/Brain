import os
import chromadb
from chromadb.utils.embedding_functions import GoogleGenerativeAiEmbeddingFunction
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
AGENT_DIR = os.path.expanduser("~/Documents/Brain/brain-agent")
CHROMA_DB_DIR = os.path.join(AGENT_DIR, "chroma_db")

chroma_client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
embedding_fn_query = GoogleGenerativeAiEmbeddingFunction(
    api_key=GEMINI_API_KEY,
    task_type="RETRIEVAL_QUERY",
    model_name="models/gemini-embedding-001"
)

collection = chroma_client.get_collection(
    name="vault_notes",
    embedding_function=GoogleGenerativeAiEmbeddingFunction(
        api_key=GEMINI_API_KEY,
        task_type="RETRIEVAL_DOCUMENT",
        model_name="models/gemini-embedding-001"
    )
)

def verify_search(query_text):
    print(f"Searching for: '{query_text}'")
    query_embeddings = embedding_fn_query([query_text])
    results = collection.query(
        query_embeddings=query_embeddings,
        n_results=3,
        include=["documents", "distances", "metadatas"]
    )
    
    if not results or not results['ids'][0]:
        print("No results found.")
        return

    for i, (doc, dist, metadata) in enumerate(zip(results['documents'][0], results['distances'][0], results['metadatas'][0])):
        print(f"\nResult {i+1} (Distance: {dist:.4f}):")
        print(f"File: {metadata['filepath']}")
        print(f"Snippet: {doc[:200]}...")

if __name__ == "__main__":
    verify_search("Psychology of Money")
    print("-" * 20)
    verify_search("Go-Giver principles")
