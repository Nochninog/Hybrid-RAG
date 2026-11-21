import unittest

from backend.ingestion.chunking import chunk_document
from backend.ingestion.markdown_document import parse_markdown
from backend.ingestion.models import DocumentBlock, ParsedDocument


class ChunkingTests(unittest.TestCase):
    # Счётчик символов делает границы предсказуемыми без внешнего токенизатора.
    def test_small_blocks_are_combined_with_source_positions(self):
        document = parse_markdown(7, "# Отпуск\n\nПервый.\n\nВторой.")
        chunks = chunk_document(document, 100, len)
        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertEqual(chunk.text, "Отпуск\n\nПервый.\n\nВторой.")
        self.assertEqual(chunk.document_id, 7)
        self.assertEqual(chunk.block_positions, (1, 2))
        self.assertEqual(chunk.token_count, len(chunk.text))

    def test_heading_path_changes_without_mixing_sections(self):
        document = parse_markdown(1, "# A\n\nВвод достаточно длинный\n\n### B\n\nПервый длинный текст\n\n## C\n\nВторой длинный текст\n\n# D\n\nТретий длинный текст")
        chunks = chunk_document(document, 100, len)
        self.assertEqual([c.headings for c in chunks], [("A",), ("A", "B"), ("A", "C"), ("D",)])
        self.assertEqual([c.position for c in chunks], [0, 1, 2, 3])
        self.assertEqual(chunks[1].text, "A\nB\n\nПервый длинный текст")

    def test_short_intro_is_merged_forward(self):
        document = parse_markdown(7, "Название\n\n# Раздел\n\nОсновной текст документа.")
        chunks = chunk_document(document, 100, len)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "Название\n\nРаздел\n\nОсновной текст документа.")
        self.assertEqual(chunks[0].headings, ())
        self.assertEqual(chunks[0].block_positions, (0, 2))

    def test_merging_preserves_both_sections_and_common_heading(self):
        document = parse_markdown(1, "# A\n\n## B\n\nx\n\n## C\n\nДостаточно длинный текст.")
        chunks = chunk_document(document, 100, len)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "A\nB\n\nx\n\nA\nC\n\nДостаточно длинный текст.")
        self.assertEqual(chunks[0].headings, ("A",))
        self.assertEqual(chunks[0].token_count, len(chunks[0].text))

    def test_short_chunk_stays_separate_if_merge_exceeds_limit(self):
        document = parse_markdown(1, "Ввод\n\n# H\n\n" + "x" * 17)
        chunks = chunk_document(document, 20, len)
        self.assertEqual([c.text for c in chunks], ["Ввод", "H\n\n" + "x" * 17])
        self.assertEqual([c.position for c in chunks], [0, 1])

    def test_unrelated_heading_paths_are_preserved_in_text(self):
        document = parse_markdown(1, "# A\n\nx\n\n# B\n\nДостаточно длинный текст.")
        chunks = chunk_document(document, 100, len)
        self.assertEqual(chunks[0].headings, ())
        self.assertEqual(chunks[0].text, "A\n\nx\n\nB\n\nДостаточно длинный текст.")

    def test_default_limit_is_512(self):
        document = ParsedDocument(1, (DocumentBlock(0, "paragraph", "x" * 513),))
        chunks = chunk_document(document, count_tokens=len)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(c.token_count <= 512 for c in chunks))
        self.assertEqual("".join(c.text for c in chunks), "x" * 513)

    def test_long_blocks_preserve_text_and_limit_including_headings(self):
        for kind in ("paragraph", "list", "table", "code"):
            for body in ("Строка с пробелами\n" * 20, "я🙂" * 60):
                with self.subTest(kind=kind, body=body[:10]):
                    document = ParsedDocument(3, (
                        DocumentBlock(0, "heading", "Раздел", 1),
                        DocumentBlock(1, kind, body),
                    ))
                    chunks = chunk_document(document, 30, len)
                    self.assertGreater(len(chunks), 1)
                    self.assertEqual("".join(c.text.removeprefix("Раздел\n\n") for c in chunks), body)
                    self.assertTrue(all(c.token_count <= 30 for c in chunks))
                    self.assertTrue(all(c.block_positions == (1,) for c in chunks))

    def test_whole_blocks_are_kept_when_they_fit_separately(self):
        document = parse_markdown(1, "12345\n\n67890")
        chunks = chunk_document(document, 5, len)
        self.assertEqual([c.text for c in chunks], ["12345", "67890"])
        self.assertEqual([c.block_positions for c in chunks], [(0,), (1,)])

    def test_empty_documents_and_headings_without_body(self):
        for text in ("", "# Только заголовок"):
            self.assertEqual(chunk_document(parse_markdown(1, text), 20, len), ())

    def test_invalid_limit_and_heading_over_budget(self):
        document = parse_markdown(1, "# Очень длинный заголовок\n\nx")
        for limit in (0, -1, 5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                chunk_document(document, limit, len)


if __name__ == "__main__":
    unittest.main()
