"""Short-lived PostgreSQL connections through Neon's managed pooler."""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Match the CLI: .env.local takes precedence over .env; injected variables win.
load_dotenv(PROJECT_ROOT / ".env.local", override=False)
load_dotenv(PROJECT_ROOT / ".env", override=False)


class DatabaseNotConfigured(RuntimeError):
    pass


def connect_database(*, for_migrations: bool = False) -> psycopg.Connection:
    variable = "DATABASE_URL_UNPOOLED" if for_migrations else "DATABASE_URL"
    url = os.environ.get(variable, "").strip()
    if not url:
        raise DatabaseNotConfigured(f"Set {variable} in .env.local, .env, or Vercel settings.")

    # Neon manages the pool. Avoid an additional per-function pool and disable
    # prepared statements so connections work with transaction pooling.
    connection = psycopg.connect(
        url,
        connect_timeout=10,
        prepare_threshold=None,
    )
    try:
        # PgBouncer rejects statement_timeout in startup options. Keep this
        # transaction-local so it cannot leak to the next pooled client.
        connection.execute("SET LOCAL statement_timeout = '10s'")
    except psycopg.Error:
        connection.close()
        raise
    return connection
