import json
import os
import unittest
from unittest.mock import MagicMock, patch

import psycopg

from server.database import DatabaseNotConfigured, connect_database
from server.main import database_health


class DatabaseHealthTests(unittest.TestCase):
    def test_schema_setup_requires_the_direct_connection_url(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://pooled", "DATABASE_URL_UNPOOLED": ""}):
            with self.assertRaises(DatabaseNotConfigured):
                connect_database(for_migrations=True)

    def test_schema_setup_uses_direct_url_without_changing_app_url(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://pooled", "DATABASE_URL_UNPOOLED": "postgresql://direct"}):
            with patch("server.database.psycopg.connect") as connect:
                connect_database(for_migrations=True)
                self.assertEqual(connect.call_args.args[0], "postgresql://direct")
                connect_database()
                self.assertEqual(connect.call_args.args[0], "postgresql://pooled")

    def test_missing_configuration_does_not_attempt_network(self):
        with patch.dict(os.environ, {"DATABASE_URL": ""}), patch("server.database.psycopg.connect") as connect:
            with self.assertRaises(DatabaseNotConfigured):
                connect_database()
            connect.assert_not_called()

    def test_missing_configuration_is_service_unavailable(self):
        with patch("server.main.connect_database", side_effect=DatabaseNotConfigured):
            response = database_health()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.body)["status"], "not_configured")

    def test_connection_error_does_not_expose_credentials(self):
        with patch("server.main.connect_database", side_effect=psycopg.OperationalError("secret-password")):
            response = database_health()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret-password", response.body.decode())

    def test_missing_extension_is_not_healthy(self):
        connection = MagicMock()
        connection.__enter__.return_value.execute.return_value.fetchone.return_value = None
        with patch("server.main.connect_database", return_value=connection):
            response = database_health()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.body)["status"], "not_ready")

    def test_missing_tables_are_not_healthy(self):
        connection = MagicMock()
        connection.__enter__.return_value.execute.return_value.fetchone.side_effect = [("0.8",), (0,), (None, None)]
        with patch("server.main.connect_database", return_value=connection):
            response = database_health()
        self.assertEqual(response.status_code, 503)

    @unittest.skipUnless(os.environ.get("DATABASE_URL"), "Neon DATABASE_URL is not configured")
    def test_live_pgvector_storage_and_retrieval(self):
        # Roll back the sample document so this test leaves no data behind.
        connection = connect_database()
        try:
            document_id = connection.execute(
                "INSERT INTO documents (filename) VALUES (%s) RETURNING id",
                ("database-check.txt",),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO document_chunks
                   (document_id, chunk_index, content, embedding_model, embedding)
                   VALUES (%s, 0, %s, %s, %s::vector)""",
                (document_id, "Database integration check", "test-only", "[1,0,0]"),
            )
            row = connection.execute(
                """SELECT content, embedding <=> %s::vector AS distance
                   FROM document_chunks WHERE document_id = %s
                   ORDER BY distance LIMIT 1""",
                ("[1,0,0]", document_id),
            ).fetchone()
            self.assertEqual(row[0], "Database integration check")
            self.assertAlmostEqual(row[1], 0)
        finally:
            connection.rollback()
            connection.close()


if __name__ == "__main__":
    unittest.main()
