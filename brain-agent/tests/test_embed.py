import os
from dotenv import load_dotenv
load_dotenv()
import google.generativeai as genai
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

try:
    res = genai.embed_content(
        model="models/text-embedding-004",
        content="Hello world",
        task_type="RETRIEVAL_DOCUMENT"
    )
    print("Success: models/text-embedding-004")
except Exception as e:
    print(f"Error with models: {e}")

try:
    res = genai.embed_content(
        model="text-embedding-004",
        content="Hello world",
        task_type="RETRIEVAL_DOCUMENT"
    )
    print("Success: text-embedding-004")
except Exception as e:
    print(f"Error without models: {e}")

