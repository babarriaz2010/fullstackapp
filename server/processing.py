"""Page-aware text extraction, overlapping chunks, and selectable embeddings."""

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import PurePosixPath

from pypdf import PdfReader
from fastapi import HTTPException
from server import gateway, local_embeddings

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
MAX_PAGES = 100
MAX_TEXT_CHARS = 200_000
MAX_CHUNKS = 250
EMBEDDING_BATCH_SIZE = 16


from server.processing_errors import ProcessingError


@dataclass(frozen=True)
class TextChunk:
    content: str
    page_number: int | None
    start_char: int
    end_char: int


@dataclass
class PreparedDocument:
    chunks: list[TextChunk]
    embeddings: list[list[float]]
    model: str
    dimensions: int
    page_count: int


def embedding_model() -> str:
    return os.environ.get("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:latest").strip()
    # Vercel alternative: return gateway.embedding_model()


def extract_pages(filename: str, content: bytes) -> list[tuple[int | None, str]]:
    if PurePosixPath(filename).suffix.lower() == ".txt":
        try:
            pages = [(None, content.decode("utf-8-sig"))]
        except UnicodeDecodeError:
            raise ProcessingError("TXT files must use UTF-8 encoding.") from None
    elif PurePosixPath(filename).suffix.lower() == ".pdf":
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ProcessingError("Please upload a PDF without password protection.")
            if len(reader.pages) > MAX_PAGES:
                raise ProcessingError(f"Please use a PDF with {MAX_PAGES} pages or fewer.")
            pages = []
            total_chars = 0
            for number, page in enumerate(reader.pages, start=1):
                stream = page.get_contents()
                if stream is not None and len(stream.get_data()) > 10 * 1024 * 1024:
                    raise ProcessingError("This PDF page is too complex. Please use a smaller PDF.")
                text = page.extract_text() or ""
                total_chars += len(text)
                if total_chars > MAX_TEXT_CHARS:
                    raise ProcessingError("This document contains too much text. Please split it into smaller documents.")
                pages.append((number, text))
        except ProcessingError:
            raise
        except Exception:
            raise ProcessingError("Could not read this PDF. Please upload a valid text-based PDF.") from None
    else:
        raise ProcessingError("Only PDF and TXT files can be processed.")

    if sum(len(text) for _, text in pages) > MAX_TEXT_CHARS:
        raise ProcessingError("This document contains too much text. Please split it into smaller documents.")
    return [(number, text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")) for number, text in pages]


def split_pages(pages: list[tuple[int | None, str]]) -> list[TextChunk]:
    chunks = []
    for page_number, text in pages:
        start = 0
        while start < len(text):
            end = min(start + CHUNK_SIZE, len(text))
            if end < len(text):
                # Prefer a word boundary without allowing the overlap to stall.
                boundary = max(text.rfind(" ", start, end), text.rfind("\n", start, end))
                if boundary > start + CHUNK_SIZE // 2:
                    end = boundary
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(TextChunk(chunk_text, page_number, start, end))
                if len(chunks) > MAX_CHUNKS:
                    raise ProcessingError("This document produces too many chunks. Please split it into smaller documents.")
            if end == len(text):
                break
            start = max(start + 1, end - CHUNK_OVERLAP)
    if not chunks:
        raise ProcessingError("No readable text was found. Scanned PDFs need OCR before uploading.")
    return chunks


def embed_texts(texts: list[str], *, model: str, purpose: str = "document") -> list[list[float]]:
    return local_embeddings.embed_texts(texts, model=model, purpose=purpose)
    # Vercel alternative (convert HTTPException to ProcessingError for uploads):
    # try:
    #     return gateway.embed_texts(texts, model=model, purpose=purpose)
    # except HTTPException as error:
    #     raise ProcessingError(str(error.detail), error.status_code) from None


def prepare_document(filename: str, content: bytes) -> PreparedDocument:
    pages = extract_pages(filename, content)
    chunks = split_pages(pages)
    model = embedding_model()
    vectors = embed_texts([chunk.content for chunk in chunks], model=model)
    return PreparedDocument(chunks, vectors, model, len(vectors[0]), len(pages))
