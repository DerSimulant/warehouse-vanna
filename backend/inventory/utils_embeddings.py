import os
from typing import List
from openai import OpenAI

EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

_client = None
def _client_lazy():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client

def embed_text(text: str) -> List[float]:
    text = (text or "").strip()
    if not text:
        return []
    cli = _client_lazy()
    resp = cli.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding
