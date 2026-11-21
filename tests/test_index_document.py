import unittest
from unittest.mock import patch
from uuid import UUID

from backend.database.errors import DatabaseError, DatabaseWriteError
from backend.ingestion.index_document import index_document
from backend.ingestion.models import DocumentChunk


class IndexDocumentTests(unittest.TestCase):
    def setUp(self):
        self.read = self.enterContext(patch(
            "corpdb.ingestion.index_document.read_document",
            return_value=("bucket", "original.md"),
        ))
        self.chunks = tuple(
            DocumentChunk(7, i, text, (), (), 2)
            for i, text in enumerate(("First text", "Second text"))
        )
        self.process = self.enterContext(patch(
            "corpdb.ingestion.index_document.process_document",
            return_value=self.chunks,
        ))
        self.embed = self.enterContext(patch(
            "corpdb.ingestion.index_document.embed_texts",
            return_value=[[0.1] * 1024, [0.2] * 1024],
        ))
        self.connection = self.enterContext(patch(
            "corpdb.ingestion.index_document.create_connection"
        ))
        self.client = self.connection.return_value.__enter__.return_value
        self.insert = self.client.collections.use.return_value.data.insert
        self.activate = self.enterContext(patch(
            "corpdb.ingestion.index_document.activate_document_index"
        ))
        self.activate.return_value = UUID(int=1)
        self.cleanup = self.enterContext(patch(
            "corpdb.ingestion.index_document.cleanup_document_index"
        ))

    def test_records_all_chunks_with_one_connection_and_run(self):
        run_id = index_document(7, ".md")
        self.assertIsInstance(run_id, UUID)
        self.process.assert_called_once_with(7, ".md")
        self.embed.assert_called_once_with([c.text for c in self.chunks])
        self.connection.assert_called_once_with()
        self.assertEqual(self.insert.call_count, 2)
        ids = []
        for i, call in enumerate(self.insert.call_args_list):
            properties = call.kwargs["properties"]
            self.assertEqual(properties, {
                "document_id": 7, "index_run_id": str(run_id),
                "storage_key": "original.md", "position": i,
                "text": self.chunks[i].text, "token_count": 2,
            })
            self.assertEqual(call.kwargs["vector"], {"qwen": self.embed.return_value[i]})
            ids.append(call.kwargs["uuid"])
        self.assertNotEqual(*ids)
        self.connection.return_value.__exit__.assert_called_once()
        self.activate.assert_called_once_with(7, "bucket", "original.md", run_id)
        self.cleanup.assert_called_once_with(7, run_id, UUID(int=1))

    def test_empty_document_does_not_call_external_services(self):
        self.process.return_value = ()
        run_id = index_document(7, ".md")
        self.assertIsInstance(run_id, UUID)
        self.activate.assert_called_once_with(7, "bucket", "original.md", run_id)
        self.embed.assert_not_called()
        self.connection.assert_not_called()

    def test_vector_count_mismatch_does_not_write(self):
        self.embed.return_value = [[0.1] * 1024]
        with self.assertRaises(ValueError):
            index_document(7, ".md")
        self.connection.assert_not_called()
        self.activate.assert_not_called()

    def test_replaced_original_is_not_indexed_under_old_key(self):
        self.read.side_effect = [("bucket", "old.md"), ("bucket", "new.md")]
        with self.assertRaises(ValueError):
            index_document(7, ".md")
        self.embed.assert_not_called()
        self.connection.assert_not_called()
        self.activate.assert_not_called()

    def test_partial_write_failure_is_not_reported_as_success(self):
        self.insert.side_effect = [UUID(int=1), RuntimeError("write failed")]
        with self.assertRaisesRegex(RuntimeError, "write failed"):
            index_document(7, ".md")
        self.connection.return_value.__exit__.assert_called_once()
        self.activate.assert_not_called()
        self.cleanup.assert_not_called()

    def test_activation_happens_after_all_inserts_and_connection_closure(self):
        def activate(*args):
            self.assertEqual(self.insert.call_count, 2)
            self.connection.return_value.__exit__.assert_called_once()

        self.activate.side_effect = activate
        index_document(7, ".md")

    def test_activation_failure_does_not_report_success_or_remove_fragments(self):
        for error in (DatabaseWriteError("replaced"), DatabaseError("unknown commit")):
            with self.subTest(error=type(error).__name__):
                self.activate.side_effect = error
                with self.assertRaises(type(error)):
                    index_document(7, ".md")
        self.client.collections.use.return_value.data.delete_many.assert_not_called()
        self.cleanup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
