"""Vercel AI Gateway transport; credentials stay on the FastAPI server."""

import json
import math
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException


def embedding_model() -> str:
    return os.environ.get('AI_GATEWAY_EMBEDDING_MODEL', 'openai/text-embedding-3-small').strip()


def chat_model() -> str:
    return os.environ.get('AI_GATEWAY_CHAT_MODEL', 'meta/llama-3.3-70b').strip()


def request_json(endpoint: str, payload: dict, *, timeout: float = 60) -> dict:
    key = os.environ.get('AI_GATEWAY_API_KEY') or os.environ.get('VERCEL_OIDC_TOKEN')
    if not key:
        raise HTTPException(503, 'Set AI_GATEWAY_API_KEY in .env.local and in Vercel environment settings, then restart the backend.')
    request = Request('https://ai-gateway.vercel.sh/v1/' + endpoint,
                      data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise HTTPException(502, 'AI Gateway returned an oversized response.')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError('Expected an object')
            return result
    except HTTPError as error:
        if error.code == 403:
            try:
                reason = json.loads(error.read(8192)).get('error', {}).get('type')
            except (ValueError, AttributeError, TypeError):
                reason = None
            if reason == 'customer_verification_required':
                raise HTTPException(503, 'Vercel AI Gateway requires a credit card on your team account. Open the AI Gateway dashboard and complete billing verification.') from None
        if error.code in (401, 403):
            raise HTTPException(503, 'AI Gateway rejected the credential. Check AI_GATEWAY_API_KEY.') from None
        if error.code == 402:
            raise HTTPException(503, 'AI Gateway needs credits. Check your Vercel AI Gateway billing.') from None
        if error.code == 429:
            raise HTTPException(429, 'AI Gateway is busy. Please try again shortly.') from None
        raise HTTPException(502, 'AI Gateway could not complete the request. Check the configured model and Gateway dashboard.') from None
    except TimeoutError:
        raise HTTPException(504, 'AI Gateway took too long. Please try again.') from None
    except (URLError, OSError):
        raise HTTPException(503, 'Cannot reach Vercel AI Gateway. Please try again.') from None
    except (ValueError, UnicodeError):
        raise HTTPException(502, 'AI Gateway returned an invalid response.') from None


def embed_texts(texts: list[str], *, model: str, purpose: str = 'document') -> list[list[float]]:
    vectors = []
    dimensions = None
    deadline = time.monotonic() + 120
    for offset in range(0, len(texts), 16):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HTTPException(504, 'Embedding generation took too long. Please use a smaller document.')
        batch = texts[offset:offset + 16]
        data = request_json('embeddings', {'model': model, 'input': batch, 'encoding_format': 'float'}, timeout=min(60, remaining)).get('data')
        if not isinstance(data, list) or len(data) != len(batch):
            raise HTTPException(502, 'AI Gateway returned an unexpected number of embeddings.')
        if any(not isinstance(item, dict) or type(item.get('index')) is not int for item in data):
            raise HTTPException(502, 'AI Gateway returned invalid embedding indexes.')
        data = sorted(data, key=lambda item: item['index'])
        if [item['index'] for item in data] != list(range(len(batch))):
            raise HTTPException(502, 'AI Gateway returned invalid embedding indexes.')
        for item in data:
            vector = item.get('embedding')
            if (not isinstance(vector, list) or not 1 <= len(vector) <= 4096
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector)
                    or not any(vector) or dimensions is not None and len(vector) != dimensions):
                raise HTTPException(502, 'AI Gateway returned an invalid embedding vector.')
            dimensions = len(vector)
            vectors.append(vector)
    return vectors


def generate_chat(messages: list[dict], model: str) -> str:
    result = request_json('chat/completions', {'model': model, 'messages': messages,
                          'stream': False, 'temperature': 0.1, 'max_tokens': 512})
    try:
        answer = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        answer = None
    if not isinstance(answer, str) or not answer.strip():
        raise HTTPException(502, 'AI Gateway returned an empty answer. Please try again.')
    return answer.strip()
