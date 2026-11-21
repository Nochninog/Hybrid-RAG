"""Проверки сохранности объектов при сбоях загрузки без внешних сервисов."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg

from backend.cli import main
from backend.database.client import transaction_connection
from backend.database.errors import DatabaseError, DatabaseWriteError
from backend.documents.operations import upload_document
from backend.storage.errors import DeleteError, UploadError


class UploadReliabilityTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="corpdb-reliability-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "report.md"
        self.path.write_bytes(b"original document")
        self.upload = self.enterContext(patch("corpdb.documents.operations.upload_file"))
        self.upload.return_value = {"bucket": "test-bucket", "key": "new-key.md"}
        self.insert = self.enterContext(patch("corpdb.documents.operations.insert_document"))
        self.insert.return_value = (42, None)
        self.delete = self.enterContext(patch("corpdb.documents.operations.delete_file"))

    def test_new_document_returns_metadata_without_deletion(self):
        document, storage, document_id = upload_document(self.path, "test-bucket")
        self.assertEqual(document_id, 42)
        self.assertEqual(storage["key"], "new-key.md")
        self.insert.assert_called_once_with(
            filename="report.md", storage_bucket="test-bucket",
            storage_key="new-key.md", size_bytes=17,
        )
        self.delete.assert_not_called()
        self.assertEqual(document.path, self.path.resolve())
        self.assertEqual(self.path.read_bytes(), b"original document")

    def test_replacement_deletes_old_object_after_database_success(self):
        events = []
        self.insert.side_effect = lambda **kwargs: (events.append("database") or (42, "old-key.md"))
        self.delete.side_effect = lambda *args: events.append(args)
        upload_document(self.path)
        self.assertEqual(events, ["database", ("test-bucket", "old-key.md")])

    def test_write_failure_deletes_only_new_object(self):
        self.insert.side_effect = DatabaseWriteError("write failed")
        with self.assertRaises(DatabaseWriteError):
            upload_document(self.path)
        self.delete.assert_called_once_with("test-bucket", "new-key.md")

    def test_cleanup_failure_preserves_original_database_error(self):
        error = DatabaseWriteError("write failed")
        self.insert.side_effect = error
        self.delete.side_effect = DeleteError("cleanup failed")
        with self.assertLogs("corpdb.documents.operations", level="WARNING") as logs:
            with self.assertRaises(DatabaseWriteError) as caught:
                upload_document(self.path)
        self.assertIs(caught.exception, error)
        self.assertIn("new-key.md", " ".join(logs.output))

    def test_unknown_commit_does_not_delete_any_object(self):
        self.insert.side_effect = DatabaseError("commit failed")
        with self.assertRaises(DatabaseError):
            upload_document(self.path)
        self.delete.assert_not_called()

    def test_old_object_cleanup_failure_still_returns_saved_document(self):
        self.insert.return_value = (42, "old-key.md")
        self.delete.side_effect = DeleteError("cleanup failed")
        with self.assertLogs("corpdb.documents.operations", level="WARNING"):
            self.assertEqual(upload_document(self.path)[2], 42)
        self.delete.assert_called_once_with("test-bucket", "old-key.md")

    def test_upload_failure_does_not_write_metadata_or_delete_objects(self):
        self.upload.side_effect = UploadError("upload failed")
        with self.assertRaises(UploadError):
            upload_document(self.path)
        self.insert.assert_not_called()
        self.delete.assert_not_called()

    def test_each_upload_gets_a_new_object_key(self):
        upload_document(self.path)
        upload_document(self.path)
        keys = [call.args[2] for call in self.upload.call_args_list]
        self.assertNotEqual(keys[0], keys[1])
        self.assertTrue(all(key.endswith(".md") for key in keys))


class TransactionErrorTests(unittest.TestCase):
    def test_connection_failure_is_write_error(self):
        with patch("corpdb.database.client.create_connection", side_effect=psycopg.OperationalError("offline")):
            with self.assertRaises(DatabaseWriteError):
                with transaction_connection():
                    self.fail("connection was not created")

    def test_statement_error_is_write_error_with_original_cause(self):
        connection = MagicMock()
        connection.__exit__.return_value = False
        error = psycopg.ProgrammingError("statement failed")
        with patch("corpdb.database.client.create_connection", return_value=connection):
            with self.assertRaises(DatabaseWriteError) as caught:
                with transaction_connection():
                    raise error
        self.assertIs(caught.exception.__cause__, error)

    def test_commit_failure_is_general_database_error(self):
        connection = MagicMock()
        connection.__exit__.side_effect = psycopg.OperationalError("connection lost at commit")
        with patch("corpdb.database.client.create_connection", return_value=connection):
            with self.assertRaises(DatabaseError) as caught:
                with transaction_connection():
                    pass
        self.assertIs(type(caught.exception), DatabaseError)

    def test_success_exits_connection_without_error(self):
        connection = MagicMock()
        with patch("corpdb.database.client.create_connection", return_value=connection):
            with transaction_connection() as actual:
                self.assertIs(actual, connection.__enter__.return_value)
        connection.__exit__.assert_called_once_with(None, None, None)

    def test_cli_reports_both_database_errors_without_traceback(self):
        for error in (DatabaseWriteError("write failed"), DatabaseError("commit failed")):
            with self.subTest(error=type(error).__name__):
                output = io.StringIO()
                with patch("sys.argv", ["corpdb", "report.md"]), patch("corpdb.cli.upload_document", side_effect=error), redirect_stdout(output):
                    self.assertEqual(main(), 1)
                self.assertIn(str(error), output.getvalue())
                self.assertNotIn("Traceback", output.getvalue())


if __name__ == "__main__":
    unittest.main()
