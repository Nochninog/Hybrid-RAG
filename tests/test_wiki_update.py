"""Updating content must not overwrite a changed page or its source associations."""
import unittest
from unittest.mock import MagicMock

from backend.database.errors import DatabaseError
from backend.database.update_wiki_page import update_wiki_page_content


class WikiUpdateTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.return_value = ('Title', 'Old')
        self.cursor.fetchall.return_value = [(47,), (48,)]

    def update(self, content='New'):
        update_wiki_page_content(10, 'Title', 'Old', content, [48, 47, 47], connection=self.connection)

    def test_only_content_changes_with_lock_and_existing_sources(self):
        self.update()
        calls = self.cursor.execute.call_args_list
        self.assertIn('FOR UPDATE', calls[0].args[0])
        self.assertEqual(calls[-1].args, ('UPDATE wiki_pages SET content=%s WHERE id=%s', ('New', 10)))
        self.connection.commit.assert_not_called()
        self.cursor.executemany.assert_not_called()

    def test_changed_missing_or_renamed_page_is_not_overwritten(self):
        for result in [None, ('Title', 'User edit'), ('Other title', 'Old')]:
            with self.subTest(result=result):
                self.cursor.reset_mock()
                self.cursor.fetchone.return_value = result
                with self.assertRaises(DatabaseError):
                    self.update()
                self.assertEqual(self.cursor.execute.call_count, 1)

    def test_changed_sources_are_not_overwritten(self):
        self.cursor.fetchall.return_value = [(47,), (49,)]
        with self.assertRaises(DatabaseError):
            self.update()
        self.assertEqual(self.cursor.execute.call_count, 2)

    def test_empty_draft_does_not_query_database(self):
        with self.assertRaises(ValueError):
            self.update(' \n')
        self.connection.cursor.assert_not_called()


if __name__ == '__main__':
    unittest.main()
