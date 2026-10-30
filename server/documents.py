"""Upload source documents and index their text with local Ollama embeddings."""

import json
from pathlib import PurePosixPath
from uuid import UUID

import psycopg
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from urllib.parse import quote

from server.database import DatabaseNotConfigured, connect_database
from server.processing import PreparedDocument, ProcessingError, prepare_document, embedding_model

router = APIRouter(prefix="/api/documents", tags=["documents"])
MAX_FILE_BYTES = 4 * 1024 * 1024
FILE_TYPES = {".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8"}


def validate_file(filename: str | None, content: bytes) -> tuple[str, str]:
    name = PurePosixPath((filename or "").replace("\\", "/")).name
    if not name or len(name) > 255 or any(ord(char) < 32 for char in name):
        raise HTTPException(400, "Choose a file with a valid filename (up to 255 characters).")
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in FILE_TYPES:
        raise HTTPException(415, "Only PDF and TXT files are supported.")
    if not content:
        raise HTTPException(400, "The selected file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "Files must be 4 MB or smaller.")
    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(400, "This file does not have a valid PDF header.")
    if suffix == ".txt":
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(400, "TXT files must use UTF-8 encoding.") from None
        if b"\x00" in content:
            raise HTTPException(400, "Choose a plain text file.")
    return name, FILE_TYPES[suffix]


def unavailable() -> HTTPException:
    return HTTPException(503, "Document storage is unavailable. Check the database connection.")


def ready_metadata(prepared: PreparedDocument) -> dict:
    return {
        "status": "ready",
        "chunk_count": len(prepared.chunks),
        "embedding_model": prepared.model,
        "embedding_dimensions": prepared.dimensions,
        "page_count": prepared.page_count,
    }


def store_chunks(cursor, document_id: UUID, prepared: PreparedDocument) -> None:
    cursor.executemany(
        """INSERT INTO document_chunks
           (document_id, chunk_index, content, page_number, embedding_model, embedding, metadata)
           VALUES (%s, %s, %s, %s, %s, %s::vector, %s)""",
        [
            (document_id, index, chunk.content, chunk.page_number, prepared.model,
             json.dumps(vector, allow_nan=False), Jsonb({"start_char": chunk.start_char, "end_char": chunk.end_char}))
            for index, (chunk, vector) in enumerate(zip(prepared.chunks, prepared.embeddings, strict=True))
        ],
    )


def prepare_or_error(filename: str, content: bytes) -> PreparedDocument:
    try:
        return prepare_document(filename, content)
    except ProcessingError as error:
        raise HTTPException(error.status_code, str(error)) from None


@router.post("", status_code=201)
def upload_document(file: UploadFile = File(...)):
    try:
        content = file.file.read(MAX_FILE_BYTES + 1)
        filename, content_type = validate_file(file.filename, content)
        # Do model work before opening a database transaction. A failed upload
        # leaves neither a partial document nor partial chunks in the library.
        prepared = prepare_or_error(filename, content)
        metadata = {"size_bytes": len(content), "content_type": content_type, **ready_metadata(prepared)}
        try:
            with connect_database() as connection:
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        """INSERT INTO documents (filename, metadata, file_content)
                           VALUES (%s, %s, %s)
                           RETURNING id, filename, metadata, created_at""",
                        (filename, Jsonb(metadata), content),
                    )
                    document = cursor.fetchone()
                    store_chunks(cursor, document["id"], prepared)
                    return {**document, "downloadable": True}
        except (DatabaseNotConfigured, psycopg.Error):
            raise unavailable() from None
    finally:
        file.file.close()


@router.get("")
def list_documents():
    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """SELECT d.id, d.filename, d.metadata, d.created_at,
                              d.file_content IS NOT NULL AS downloadable,
                              (SELECT count(*) FROM document_chunks c WHERE c.document_id = d.id) AS chunk_count
                       FROM documents d ORDER BY d.created_at DESC, d.id DESC LIMIT 100"""
                )
                documents = cursor.fetchall()
                active_model = embedding_model()
                for document in documents:
                    document['needs_reprocessing'] = document['metadata'].get('embedding_model') != active_model or document['chunk_count'] == 0
                return {"documents": documents}
    except (DatabaseNotConfigured, psycopg.Error):
        raise unavailable() from None


@router.post("/{document_id}/process")
def process_document(document_id: UUID):
    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT id, filename, metadata, file_content, created_at FROM documents WHERE id = %s", (document_id,))
                document = cursor.fetchone()
    except (DatabaseNotConfigured, psycopg.Error):
        raise unavailable() from None
    if document is None or document["file_content"] is None:
        raise HTTPException(404, "Document file not found.")

    prepared = prepare_or_error(document["filename"], bytes(document["file_content"]))
    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                # Serialize replacements, keeping old chunks until all new
                # embeddings exist. The transaction rolls back on any error.
                cursor.execute("SELECT id FROM documents WHERE id = %s FOR UPDATE", (document_id,))
                if cursor.fetchone() is None:
                    raise HTTPException(404, "Document file not found.")
                cursor.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))
                store_chunks(cursor, document_id, prepared)
                cursor.execute(
                    """UPDATE documents SET metadata = metadata || %s
                       WHERE id = %s RETURNING id, filename, metadata, created_at""",
                    (Jsonb(ready_metadata(prepared)), document_id),
                )
                return {**cursor.fetchone(), "downloadable": True, "chunk_count": len(prepared.chunks)}
    except (DatabaseNotConfigured, psycopg.Error):
        raise unavailable() from None


@router.get("/{document_id}/chunks")
def get_document_chunks(document_id: UUID):
    try:
        with connect_database() as connection:
            if connection.execute("SELECT id FROM documents WHERE id = %s", (document_id,)).fetchone() is None:
                raise HTTPException(404, "Document not found.")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """SELECT id, chunk_index, content, page_number, embedding_model,
                              vector_dims(embedding) AS embedding_dimensions
                       FROM document_chunks WHERE document_id = %s ORDER BY chunk_index LIMIT 250""",
                    (document_id,),
                )
                return {"document_id": document_id, "chunks": cursor.fetchall()}
    except (DatabaseNotConfigured, psycopg.Error):
        raise unavailable() from None


@router.get("/{document_id}/download")
def download_document(document_id: UUID):
    try:
        with connect_database() as connection:
            row = connection.execute(
                "SELECT filename, file_content FROM documents WHERE id = %s",
                (document_id,),
            ).fetchone()
    except (DatabaseNotConfigured, psycopg.Error):
        raise unavailable() from None
    if row is None or row[1] is None:
        raise HTTPException(404, "Document file not found.")
    content_type = FILE_TYPES.get(PurePosixPath(row[0]).suffix.lower(), "application/octet-stream")
    return Response(
        content=bytes(row[1]),
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row[0], safe='')}",
            "X-Content-Type-Options": "nosniff",
        },
    )
