from openai import OpenAI
from llama_index.readers.file import PDFReader
from llama_index.core.node_parser import SentenceSplitter
from dotenv import load_dotenv
from google import genai;
import os
load_dotenv()


GEMINI_API_KEY= os.getenv("GEMINI_API_KEY");

client = genai.Client(api_key=GEMINI_API_KEY);
EMBEDDING_MODEL="text-embedding-004"
EMBED_DIM=768

splitter = SentenceSplitter(chunk_size=1000, chunk_overlap=200)

def load_and_chunk_pdf(path: str):
    docs = PDFReader().load_data(file=path);
    texts = [d.text for d in docs if getattr(d, "text", None)]
    chunks = []
    for t in texts:
        chunks.extend(splitter.split_text(t))
    return chunks

def embed_texts(texts: list[str]) -> list[list[float]]:
    response = client.models.embed_content(
        model= EMBEDDING_MODEL,
        contents = texts
    )
    print(response)
    return [embedding.values for embedding in response.embeddings]
