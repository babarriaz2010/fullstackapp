"""FastAPI backend shared by local development and Vercel."""

from datetime import datetime, timezone

import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from server.database import DatabaseNotConfigured, connect_database
from server.chat import router as chat_router
from server.documents import router as documents_router

app = FastAPI(
    title="Fullstack App API",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.include_router(documents_router)
app.include_router(chat_router)


class MessageResponse(BaseModel):
    message: str
    timestamp: datetime


@app.get("/api/hello", response_model=MessageResponse)
async def hello() -> MessageResponse:
    return MessageResponse(
        message="Hello from the Python FastAPI backend!",
        timestamp=datetime.now(timezone.utc),
    )


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health/db", response_model=None)
def database_health():
    """Check PostgreSQL and pgvector without exposing connection credentials."""
    try:
        with connect_database() as connection:
            vector = connection.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()
            if vector is None:
                return JSONResponse(
                    status_code=503,
                    content={"status": "not_ready", "message": "Run database initialization to enable pgvector."},
                )
            connection.execute("SELECT '[1,0]'::vector <=> '[1,0]'::vector").fetchone()
            tables = connection.execute(
                "SELECT to_regclass('public.documents'), to_regclass('public.document_chunks')"
            ).fetchone()
            if not tables or not all(tables):
                return JSONResponse(
                    status_code=503,
                    content={"status": "not_ready", "message": "Run database initialization to create the RAG tables."},
                )
        return {"status": "ok", "database": "connected", "pgvector": "enabled"}
    except DatabaseNotConfigured:
        return JSONResponse(
            status_code=503,
            content={"status": "not_configured", "message": "DATABASE_URL is not configured."},
        )
    except psycopg.Error:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "message": "Database check failed. Check Neon connectivity and configuration."},
        )
