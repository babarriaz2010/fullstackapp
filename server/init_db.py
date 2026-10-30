"""Enable pgvector and initialize the RAG tables without dropping data."""

import sys
from pathlib import Path

import psycopg

from server.database import DatabaseNotConfigured, connect_database


def initialize_database() -> None:
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with connect_database(for_migrations=True) as connection:
        # Serialize concurrent setup attempts, including through the pooler.
        connection.execute("SELECT pg_advisory_xact_lock(807346251)")
        connection.execute(schema, prepare=False)


if __name__ == "__main__":
    try:
        initialize_database()
    except DatabaseNotConfigured as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except psycopg.Error:
        print(
            "Database setup failed. Check the Neon URL, connectivity, and role permissions.",
            file=sys.stderr,
        )
        sys.exit(1)
    print("Database ready: pgvector enabled; documents and document_chunks created.")
