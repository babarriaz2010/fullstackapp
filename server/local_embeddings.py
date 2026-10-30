"""Preserved local Ollama embedding implementation."""
import json
import math
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from server.processing_errors import ProcessingError

EMBEDDING_BATCH_SIZE = 16

def embed_texts(texts: list[str], *, model: str, purpose: str = "document") -> list[list[float]]:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    if os.environ.get("VERCEL") and not os.environ.get("OLLAMA_BASE_URL"):
        raise ProcessingError("Configure a reachable Ollama server for the deployed backend.", 503)
    prefix = "search_query: " if purpose == "query" else "search_document: "
    if not model.startswith("nomic-embed-text"):
        prefix = ""
    vectors = []
    dimensions = None
    deadline = time.monotonic() + 120
    for offset in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProcessingError("Embedding generation took too long. Please use a smaller document.", 504)
        batch = texts[offset:offset + EMBEDDING_BATCH_SIZE]
        request = Request(
            base_url + "/api/embed",
            data=json.dumps({"model": model, "input": [prefix + text for text in batch], "truncate": False}).encode(),
            headers={"Content-Type": "application/json"},
        )
        if os.environ.get("OLLAMA_API_KEY"):
            request.add_header("Authorization", "Bearer " + os.environ["OLLAMA_API_KEY"])
        try:
            with urlopen(request, timeout=min(60, remaining)) as response:
                payload = response.read(8 * 1024 * 1024 + 1)
                if len(payload) > 8 * 1024 * 1024:
                    raise ProcessingError("Ollama returned an oversized embedding response.", 502)
                result = json.loads(payload)
        except HTTPError as error:
            if error.code == 404:
                raise ProcessingError("The embedding model is unavailable. Start Ollama and install the configured embedding model.", 503) from None
            raise ProcessingError("Ollama could not embed this document. Check the embedding model and document size.", 502) from None
        except (URLError, TimeoutError, OSError):
            raise ProcessingError("Cannot reach Ollama. Start Ollama and try again.", 503) from None
        except (ValueError, UnicodeError):
            raise ProcessingError("Ollama returned an invalid embedding response.", 502) from None

        batch_vectors = result.get("embeddings") if isinstance(result, dict) else None
        if not isinstance(batch_vectors, list) or len(batch_vectors) != len(batch):
            raise ProcessingError("Ollama returned an unexpected number of embeddings.", 502)
        for vector in batch_vectors:
            if not isinstance(vector, list) or not 1 <= len(vector) <= 4096:
                raise ProcessingError("Ollama returned an invalid embedding vector.", 502)
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector):
                raise ProcessingError("Ollama returned invalid embedding values.", 502)
            if not any(value != 0 for value in vector):
                raise ProcessingError("Ollama returned an empty embedding vector.", 502)
            if dimensions is not None and len(vector) != dimensions:
                raise ProcessingError("Ollama returned inconsistent embedding dimensions.", 502)
            dimensions = len(vector)
            vectors.append(vector)
    return vectors

