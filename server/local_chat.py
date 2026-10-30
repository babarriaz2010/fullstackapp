"""Preserved local Ollama chat transport."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from fastapi import HTTPException


def generate_chat(messages: list[dict], model: str) -> str:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    request = Request(
        base_url + "/api/chat",
        data=json.dumps({"model": model, "messages": messages, "stream": False,
                         "options": {"temperature": 0.1, "num_predict": 512, "num_ctx": 4096}}).encode(),
        headers={"Content-Type": "application/json"},
    )
    if os.environ.get("OLLAMA_API_KEY"):
        request.add_header("Authorization", "Bearer " + os.environ["OLLAMA_API_KEY"])
    try:
        with urlopen(request, timeout=120) as response:
            payload = response.read(1024 * 1024 + 1)
            if len(payload) > 1024 * 1024:
                raise HTTPException(502, "Ollama returned an oversized chat response.")
            result = json.loads(payload)
    except HTTPError as error:
        if error.code == 404:
            raise HTTPException(503, "The chat model is unavailable. Start Ollama and install the configured chat model.") from None
        raise HTTPException(502, "Ollama could not generate an answer. Please try again.") from None
    except TimeoutError:
        raise HTTPException(504, "The chat model took too long. Please try a shorter question.") from None
    except (URLError, OSError):
        raise HTTPException(503, "Cannot reach Ollama. Start Ollama and try again.") from None
    except (ValueError, UnicodeError):
        raise HTTPException(502, "Ollama returned an invalid chat response.") from None

    message = result.get("message") if isinstance(result, dict) else None
    answer = message.get("content") if isinstance(message, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        raise HTTPException(502, "Ollama returned an empty answer. Please try again.")
    return answer.strip()
