import unittest
from unittest.mock import patch
from uuid import UUID

from backend.database.activate_document_index import activate_document_index
from backend.database.errors import DatabaseWriteError
from backend.database.insert_document import insert_document


class ActiveIndexTests(unittest.TestCase):
    def test_activation_checks_original_in_same_update(self):
        run_id = UUID(int=1)
        with patch(
            "corpdb.database.activate_document_index.transaction_connection"
        ) as transaction:
            cursor = transaction.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (UUID(int=2),)
            self.assertEqual(
                activate_document_index(7, "bucket", "original.md", run_id), UUID(int=2)
            )
            select_sql, select_parameters = cursor.execute.call_args_list[0].args
            self.assertIn("FOR UPDATE", select_sql)
            self.assertEqual(select_parameters, (7, "bucket", "original.md"))
            sql, parameters = cursor.execute.call_args.args
            sql = " ".join(sql.split())
            self.assertIn("SET active_index_run_id = %s", sql)
            self.assertIn("WHERE id = %s AND storage_bucket = %s AND storage_key = %s", sql)
            self.assertEqual(parameters, (run_id, 7, "bucket", "original.md"))
            transaction.return_value.__exit__.assert_called_once_with(None, None, None)

    def test_missing_or_replaced_document_does_not_commit_activation(self):
        with patch(
            "corpdb.database.activate_document_index.transaction_connection"
        ) as transaction:
            cursor = transaction.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = None
            with self.assertRaises(DatabaseWriteError):
                activate_document_index(7, "bucket", "old.md", UUID(int=1))
            self.assertIs(transaction.return_value.__exit__.call_args.args[0], DatabaseWriteError)

    def test_replacement_resets_active_run_in_original_update(self):
        with patch("corpdb.database.insert_document.transaction_connection") as transaction:
            cursor = transaction.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.side_effect = [None, (7, "old.md")]
            self.assertEqual(insert_document("report.md", "bucket", "new.md", 100), (7, "old.md"))
            sql, parameters = cursor.execute.call_args.args
            self.assertIn("active_index_run_id = NULL", sql)
            self.assertIn("SET storage_key = %s", sql)
            self.assertEqual(parameters, ("new.md", 100, 7))


if __name__ == "__main__":
    unittest.main()
