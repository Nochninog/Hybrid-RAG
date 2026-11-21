from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID

from weaviate.exceptions import WeaviateBaseError

from backend.indexes.delete_old_chunks import delete_old_chunks
from backend.ingestion.cleanup_document_index import cleanup_document_index


def matches_filter(condition, properties):
    if hasattr(condition, "filters"):
        values = [matches_filter(part, properties) for part in condition.filters]
        return all(values) if type(condition).__name__ == "_FilterAnd" else any(values)
    actual = properties[condition.target]
    if condition.operator.value == "Equal":
        return actual == condition.value
    return actual != condition.value


class IndexCleanupTests(unittest.TestCase):
    def test_filter_preserves_active_parallel_and_other_document(self):
        with patch("corpdb.indexes.delete_old_chunks.create_connection") as connection:
            delete = connection.return_value.__enter__.return_value.collections.use.return_value.data.delete_many
            delete.return_value = SimpleNamespace(matches=0, successful=0, failed=0)
            delete_old_chunks(7, "new.md", UUID(int=2), UUID(int=1))
            where = delete.call_args.kwargs["where"]
            for document_id, key, run, expected in (
                (7, "new.md", 2, False),  # active
                (7, "new.md", 3, False),  # parallel
                (8, "old.md", 1, False),  # another document
                (7, "new.md", 1, True),   # previously active
                (7, "old.md", 4, True),   # replaced original
            ):
                with self.subTest(document_id=document_id, key=key, run=run):
                    self.assertEqual(matches_filter(where, {
                        "document_id": document_id, "storage_key": key,
                        "index_run_id": str(UUID(int=run)),
                    }), expected)

    def test_delete_repeats_when_server_limits_number_of_objects(self):
        with patch("corpdb.indexes.delete_old_chunks.create_connection") as connection:
            delete = connection.return_value.__enter__.return_value.collections.use.return_value.data.delete_many
            delete.side_effect = [
                SimpleNamespace(matches=12000, successful=10000, failed=0),
                SimpleNamespace(matches=2000, successful=2000, failed=0),
            ]
            delete_old_chunks(7, "new.md", UUID(int=2), None)
            self.assertEqual(delete.call_count, 2)

    def test_partial_delete_failure_is_reported(self):
        with patch("corpdb.indexes.delete_old_chunks.create_connection") as connection:
            delete = connection.return_value.__enter__.return_value.collections.use.return_value.data.delete_many
            delete.return_value = SimpleNamespace(matches=2, successful=1, failed=1)
            with self.assertRaises(WeaviateBaseError):
                delete_old_chunks(7, "new.md", UUID(int=2), None)

    def test_cleanup_locks_document_and_checks_current_active_run(self):
        with patch("corpdb.database.activate_document_index.transaction_connection") as transaction, patch(
            "corpdb.ingestion.cleanup_document_index.delete_old_chunks"
        ) as delete:
            cursor = transaction.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            for row in (None, ("new.md", None), ("new.md", UUID(int=3))):
                cursor.fetchone.return_value = row
                cleanup_document_index(7, UUID(int=2), UUID(int=1))
            delete.assert_not_called()
            cursor.fetchone.return_value = ("new.md", UUID(int=2))
            cleanup_document_index(7, UUID(int=2), UUID(int=1))
            self.assertIn("FOR UPDATE", cursor.execute.call_args.args[0])
            delete.assert_called_once_with(7, "new.md", UUID(int=2), UUID(int=1))

    def test_cleanup_failure_only_warns_after_activation(self):
        with patch("corpdb.database.activate_document_index.transaction_connection") as transaction, patch(
            "corpdb.ingestion.cleanup_document_index.delete_old_chunks",
            side_effect=WeaviateBaseError("offline"),
        ):
            cursor = transaction.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = ("new.md", UUID(int=2))
            with self.assertLogs("corpdb.ingestion.cleanup_document_index", level="WARNING"):
                cleanup_document_index(7, UUID(int=2), UUID(int=1))


if __name__ == "__main__":
    unittest.main()
