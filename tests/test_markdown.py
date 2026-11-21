import unittest

from backend.ingestion.markdown_document import parse_markdown


class MarkdownTests(unittest.TestCase):
    def test_structure_and_content_are_preserved(self):
        text = (
            "# Отпуска\n\n"
            "Оформление\n----------\n\n"
            "Первый абзац\nс продолжением.\n\n"
            "3. Заявление\n   - Даты\n   - Подпись\n4. Согласование\n\n"
            "| Роль | Срок |\n| --- | --- |\n| Автор | 3 дня |\n\n"
            "```python\n# Это код\n    value = 1\n```\n"
        )
        document = parse_markdown(7, text)
        blocks = document.blocks
        self.assertEqual(document.document_id, 7)
        self.assertEqual(
            [block.kind for block in blocks],
            ["heading", "heading", "paragraph", "list", "table", "code"],
        )
        self.assertEqual([block.position for block in blocks], list(range(6)))
        self.assertEqual(
            [block.heading_level for block in blocks], [1, 2, None, None, None, None]
        )
        self.assertEqual([block.text for block in blocks], [
            "Отпуска",
            "Оформление",
            "Первый абзац\nс продолжением.",
            "3. Заявление\n   - Даты\n   - Подпись\n4. Согласование",
            "| Роль | Срок |\n| --- | --- |\n| Автор | 3 дня |",
            "```python\n# Это код\n    value = 1\n```",
        ])
        for block in blocks:
            self.assertIsNone(block.page_start)
            self.assertIsNone(block.page_end)

    def test_empty_document(self):
        self.assertEqual(parse_markdown(1, " \n\n").blocks, ())

    def test_indented_code_and_line_endings(self):
        blocks = parse_markdown(1, "    # code\r\n    x = 1\r\n\r\nText\r\n").blocks
        self.assertEqual([block.kind for block in blocks], ["code", "paragraph"])
        self.assertEqual(blocks[0].text, "    # code\n    x = 1")
        self.assertEqual(blocks[1].text, "Text")

    def test_quote_and_html_are_preserved_as_paragraphs(self):
        blocks = parse_markdown(1, "> Важно\n>\n> - Пункт\n\n<div>Текст</div>\n").blocks
        self.assertEqual([block.kind for block in blocks], ["paragraph", "paragraph"])
        self.assertEqual(blocks[0].text, "> Важно\n>\n> - Пункт")
        self.assertEqual(blocks[1].text, "<div>Текст</div>")


if __name__ == "__main__":
    unittest.main()
