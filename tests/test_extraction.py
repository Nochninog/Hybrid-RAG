import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from botocore.exceptions import BotoCoreError
from openai import OpenAIError
from weaviate.exceptions import WeaviateBaseError

from backend.cli import main
from backend.database.errors import DatabaseError
from backend.database.read_document import read_document
from backend.ingestion.errors import ExtractionError
from backend.ingestion.extraction import extraction_text
from backend.storage.errors import UploadError


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.read = self.enterContext(patch(
            "corpdb.ingestion.extraction.read_document", return_value=("bucket", "key")
        ))
        self.download = self.enterContext(patch("corpdb.ingestion.extraction.download_file"))

    def test_text_is_returned_without_printing_and_body_closed(self):
        body = io.BytesIO("Привет".encode("utf-8"))
        self.download.return_value = {"Body": body}
        output = io.StringIO()
        with redirect_stdout(output):
            content_text = extraction_text(1, ".md")
        self.assertEqual(content_text, "Привет")
        self.assertEqual(output.getvalue(), "")
        self.assertTrue(body.closed)

    def test_invalid_text_and_pdf_are_reported_and_body_closed(self):
        for extension, data in ((".txt", b"\xff"), (".pdf", b"%PDF-1.7\ninvalid")):
            with self.subTest(extension=extension):
                body = io.BytesIO(data)
                self.download.return_value = {"Body": body}
                with self.assertRaises(ExtractionError):
                    extraction_text(1, extension)
                self.assertTrue(body.closed)

    def test_read_failure_still_closes_body(self):
        body = MagicMock()
        body.read.side_effect = BotoCoreError()
        self.download.return_value = {"Body": body}
        with self.assertRaises(ExtractionError):
            extraction_text(1, ".txt")
        body.close.assert_called_once_with()

    def test_docx_is_rejected_before_reading(self):
        with self.assertRaises(ExtractionError):
            extraction_text(1, ".docx")
        self.read.assert_not_called()
        self.download.assert_not_called()

    def test_missing_document_has_application_error(self):
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value = None
        with patch("corpdb.database.read_document.transaction_connection") as transaction:
            transaction.return_value.__enter__.return_value = connection
            with self.assertRaisesRegex(DatabaseError, "не найден"):
                read_document(1)

    def test_cli_handles_extraction_errors(self):
        document = SimpleNamespace(
            original_filename="test.txt", path="test.txt", extension=".txt", size_bytes=1
        )
        for error in (
            ExtractionError("bad text"), UploadError("GET failed"),
            DatabaseError("not found"), OpenAIError("Qwen failed"),
            WeaviateBaseError("Weaviate failed"), ValueError("document replaced"),
        ):
            with self.subTest(error=type(error).__name__):
                with patch("sys.argv", ["corpdb", "test.txt"]), patch(
                    "corpdb.cli.upload_document", return_value=(document, {}, 1)
                ), patch("corpdb.cli.index_document", side_effect=error), redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main(), 1)
                self.assertIn(str(error), output.getvalue())
                self.assertNotIn("Индексация завершена", output.getvalue())


if __name__ == "__main__":
    unittest.main()
