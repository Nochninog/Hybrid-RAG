import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from backend.cli import main
from backend.ingestion.chunking import chunk_document
from backend.ingestion.errors import ExtractionError
from backend.ingestion.operations import process_document
from test_pdf import make_pdf


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.read = self.enterContext(patch(
            "corpdb.ingestion.extraction.read_document", return_value=("bucket", "key")
        ))
        self.download = self.enterContext(patch("corpdb.ingestion.extraction.download_file"))
        # Настоящие парсер и чанкер; счётчик символов исключает загрузку токенизатора.
        def count_and_chunk(document):
            self.chunks = chunk_document(document, count_tokens=len)
            return self.chunks

        self.enterContext(patch(
            "corpdb.ingestion.operations.chunk_document",
            side_effect=count_and_chunk,
        ))

    def test_cli_indexes_markdown_from_storage_and_prints_run_id(self):
        text = "# Отпуск\n\n" + "Правила отпуска. " * 100
        body = io.BytesIO(text.encode("utf-8"))
        self.download.return_value = {"Body": body}
        document = SimpleNamespace(
            original_filename="test.md", path="test.md", extension=".md",
            size_bytes=len(text.encode("utf-8")),
        )
        output = io.StringIO()
        with patch("sys.argv", ["corpdb", "test.md"]), patch(
            "corpdb.cli.upload_document", return_value=(document, {}, 7)
        ), patch(
            "corpdb.ingestion.index_document.read_document", return_value=("bucket", "key")
        ), patch(
            "corpdb.ingestion.index_document.embed_texts",
            side_effect=lambda texts: [[0.1] * 1024 for text in texts],
        ), patch(
            "corpdb.ingestion.index_document.create_connection"
        ) as connection, patch(
            "corpdb.ingestion.index_document.activate_document_index"
        ) as activate, patch(
            "corpdb.ingestion.index_document.cleanup_document_index"
        ), redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertTrue(body.closed)
        self.read.assert_called_once_with(document_id=7)
        run_id = activate.call_args.args[3]
        self.assertIn(f"Индексация завершена. Метка набора: {run_id}", output.getvalue())
        insert = connection.return_value.__enter__.return_value.collections.use.return_value.data.insert
        self.assertEqual(insert.call_count, len(self.chunks))
        self.assertGreater(len(self.chunks), 1)
        self.assertEqual(
            [call.kwargs["properties"]["text"] for call in insert.call_args_list],
            [chunk.text for chunk in self.chunks],
        )
        self.assertTrue(all(
            call.kwargs["properties"]["index_run_id"] == str(run_id)
            for call in insert.call_args_list
        ))
        self.assertTrue(all(c.document_id == 7 and c.token_count <= 512 for c in self.chunks))
        self.assertTrue(all(c.headings == ("Отпуск",) for c in self.chunks))

    def test_plain_text_keeps_markdown_symbols(self):
        for extension in (".txt",):
            with self.subTest(extension=extension), patch(
                "corpdb.ingestion.operations.extraction_text", return_value="# Это текст\n\n---"
            ), redirect_stdout(io.StringIO()) as output:
                chunks = process_document(7, extension)
                self.assertEqual(chunks[0].text, "# Это текст\n\n---")
                self.assertEqual(chunks[0].headings, ())
                self.assertEqual(output.getvalue(), "")

    def test_pdf_is_parsed_from_original_bytes_with_one_download(self):
        body = io.BytesIO(make_pdf("""
BT /F2 18 Tf 50 750 Td (Title) Tj ET
BT /F1 12 Tf 50 720 Td (A sufficiently long paragraph with ordinary text.) Tj ET
"""))
        self.download.return_value = {"Body": body}
        with patch("corpdb.ingestion.operations.extraction_text") as extract:
            chunks = process_document(7, ".pdf")
        extract.assert_not_called()
        self.download.assert_called_once_with(bucket="bucket", storage_key="key")
        self.assertTrue(body.closed)
        self.assertEqual(chunks[0].headings, ("Title",))
        self.assertIn("A sufficiently long paragraph", chunks[0].text)
        self.assertEqual(chunks[0].document_id, 7)

    def test_invalid_pdf_is_reported_after_closing_body(self):
        body = io.BytesIO(b"invalid PDF")
        self.download.return_value = {"Body": body}
        with self.assertRaises(ExtractionError):
            process_document(7, ".pdf")
        self.assertTrue(body.closed)

    def test_empty_text_returns_no_chunks(self):
        self.download.return_value = {"Body": io.BytesIO(b" \n")}
        self.assertEqual(process_document(7, ".txt"), ())
