"""Сохранение Wiki и порядок действий при генерации."""

import unittest
from unittest.mock import patch

from backend.database.insert_wiki_page import insert_wiki_page
from backend.wiki.operations import create_wiki_page, save_wiki_page


class WikiStorageTests(unittest.TestCase):
    def test_page_and_sources_share_one_transaction(self):
        with patch("corpdb.database.insert_wiki_page.transaction_connection") as transaction:
            cursor = transaction.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (7,)
            self.assertEqual(insert_wiki_page("Отпуск", "Текст", [43, 44]), 7)
            transaction.assert_called_once_with()
            self.assertEqual(cursor.execute.call_args.args[1], ("Отпуск", "Текст"))
            self.assertEqual(cursor.executemany.call_args.args[1], [(7, 43), (7, 44)])
            transaction.return_value.__exit__.assert_called_once_with(None, None, None)

    def test_save_preserves_markdown_and_deduplicates_sources(self):
        text = "# Отпуск\n\nУсловие. [Источник](document:43)\n"
        with patch("corpdb.wiki.operations.insert_wiki_page", return_value=7) as insert:
            self.assertEqual(save_wiki_page(" Отпуск ", text, [43, 44, 43]), 7)
            insert.assert_called_once_with("Отпуск", text, [43, 44])

    def test_empty_fields_do_not_write(self):
        with patch("corpdb.wiki.operations.insert_wiki_page") as insert:
            for title, content, ids in [(" ", "text", [43]), ("title", "\n", [43]), ("title", "text", [])]:
                with self.subTest(title=title, content=content, ids=ids), self.assertRaises(ValueError):
                    save_wiki_page(title, content, ids)
            insert.assert_not_called()

    def test_creation_saves_generated_text_after_model_call(self):
        with patch("corpdb.wiki.operations.prepare_wiki_messages", return_value=[{"role": "user", "content": "sources"}]) as prepare, patch(
            "corpdb.wiki.operations.insert_wiki_page", return_value=7
        ) as insert, patch("corpdb.wiki.operations.generate_text") as generate:
            def response(messages):
                insert.assert_not_called()
                return "# Отпуск\nТекст"
            generate.side_effect = response
            self.assertEqual(create_wiki_page([43, 44, 43], "Отпуск"), 7)
            prepare.assert_called_once_with([43, 44], "Отпуск")
            generate.assert_called_once_with(prepare.return_value)
            insert.assert_called_once_with("Отпуск", "# Отпуск\nТекст", [43, 44])

    def test_generation_failure_does_not_write(self):
        with patch("corpdb.wiki.operations.prepare_wiki_messages", return_value=[]), patch(
            "corpdb.wiki.operations.generate_text", side_effect=ValueError("generation failed")
        ), patch("corpdb.wiki.operations.insert_wiki_page") as insert:
            with self.assertRaises(ValueError):
                create_wiki_page([43], "Отпуск")
            insert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
