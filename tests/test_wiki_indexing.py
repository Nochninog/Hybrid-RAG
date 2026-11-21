"""Границы разделов Wiki, повторная запись и ошибки индексации."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from weaviate.exceptions import WeaviateBaseError

from backend.database.errors import DatabaseError
from backend.database.read_wiki_page import read_wiki_page
from backend.indexes.insert_wiki_chunk import delete_extra_wiki_chunks, insert_wiki_chunk
from backend.wiki.chunking import WikiChunk, chunk_wiki_page
from backend.wiki.indexing import index_wiki_page


class WikiChunkingTests(unittest.TestCase):
    def test_short_sections_are_separate_and_title_is_present_once(self):
        chunks = chunk_wiki_page(1, "Wiki", "# Wiki\n\nВвод.\n\n## A\n\nx\n\n### B\n\ny\n\n## C\n\nz", count_tokens=len)
        self.assertEqual([c.headings for c in chunks], [("Wiki",), ("Wiki", "A"), ("Wiki", "A", "B"), ("Wiki", "C")])
        self.assertEqual([c.position for c in chunks], [0, 1, 2, 3])
        self.assertTrue(all(c.text.count("Wiki") == 1 for c in chunks))

    def test_long_section_is_split_with_full_context_and_no_text_loss(self):
        body = "Фраза со ссылкой [Источник](document:43). " * 40
        chunks = chunk_wiki_page(1, "Wiki", "## Раздел\n\n" + body, 100, len)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c.token_count <= 100 and c.headings == ("Wiki", "Раздел") for c in chunks))
        reconstructed = "".join(c.text.removeprefix("Wiki\nРаздел\n\n") for c in chunks)
        self.assertEqual(reconstructed, body)

    def test_plain_text_also_gets_title_context(self):
        chunks = chunk_wiki_page(1, "Wiki", "Просто текст", count_tokens=len)
        self.assertEqual(chunks[0].text, "Wiki\n\nПросто текст")
        self.assertEqual(chunk_wiki_page(1, "Wiki", "# Wiki", count_tokens=len), ())


class WikiIndexingTests(unittest.TestCase):
    def setUp(self):
        self.read = self.enterContext(patch("corpdb.wiki.indexing.read_wiki_page", return_value=("Wiki", "text")))
        self.chunks = (WikiChunk(1, 0, "Wiki", ("Wiki",), "Wiki\n\ntext", 5),)
        self.chunk = self.enterContext(patch("corpdb.wiki.indexing.chunk_wiki_page", return_value=self.chunks))
        self.embed = self.enterContext(patch("corpdb.wiki.indexing.embed_texts", return_value=[[0.1, 0.2]]))
        factory = self.enterContext(patch("corpdb.wiki.indexing.create_connection"))
        self.client = factory.return_value.__enter__.return_value
        self.insert = self.enterContext(patch("corpdb.wiki.indexing.insert_wiki_chunk", return_value="id"))
        self.cleanup = self.enterContext(patch("corpdb.wiki.indexing.delete_extra_wiki_chunks"))

    def test_embeds_and_writes_with_one_client_then_cleans_tail(self):
        def cleanup(*args, **kwargs):
            self.insert.assert_called_once_with(self.chunks[0], [0.1, 0.2], client=self.client)
        self.cleanup.side_effect = cleanup
        self.assertEqual(index_wiki_page(1), ("id",))
        self.embed.assert_called_once_with([self.chunks[0].text])
        self.cleanup.assert_called_once_with(1, 1, client=self.client)

    def test_wrong_vector_count_and_insert_failure_do_not_clean(self):
        self.embed.return_value = []
        with self.assertRaises(ValueError):
            index_wiki_page(1)
        self.insert.assert_not_called()
        self.embed.return_value = [[0.1]]
        self.insert.side_effect = WeaviateBaseError("insert failed")
        with self.assertRaises(WeaviateBaseError):
            index_wiki_page(1)
        self.cleanup.assert_not_called()

    def test_empty_page_does_not_call_embedding_api(self):
        self.chunk.return_value = ()
        self.assertEqual(index_wiki_page(1), ())
        self.embed.assert_not_called()
        self.cleanup.assert_called_once_with(1, 0, client=self.client)

    def test_missing_page_stops_before_embedding(self):
        self.read.side_effect = DatabaseError("not found")
        with self.assertRaises(DatabaseError):
            index_wiki_page(999)
        self.embed.assert_not_called()


class WikiWriteTests(unittest.TestCase):
    def test_repeat_replaces_same_uuid_and_preserves_properties(self):
        client = MagicMock()
        data = client.collections.use.return_value.data
        data.exists.side_effect = [False, True]
        chunk = WikiChunk(1, 0, "Wiki", ("Wiki", "Раздел"), "text", 1)
        first = insert_wiki_chunk(chunk, [0.1], client=client)
        second = insert_wiki_chunk(chunk, [0.1], client=client)
        self.assertEqual(first, second)
        self.assertEqual(data.insert.call_args.kwargs, data.replace.call_args.kwargs)
        self.assertEqual(data.insert.call_args.kwargs["properties"]["headings"], ["Wiki", "Раздел"])

    def test_cleanup_repeats_limited_deletion_and_rejects_failure(self):
        client = MagicMock()
        delete = client.collections.use.return_value.data.delete_many
        delete.side_effect = [SimpleNamespace(failed=0, matches=2, successful=1), SimpleNamespace(failed=0, matches=1, successful=1)]
        delete_extra_wiki_chunks(1, 3, client=client)
        self.assertEqual(delete.call_count, 2)
        delete.side_effect = [SimpleNamespace(failed=1, matches=1, successful=0)]
        with self.assertRaises(WeaviateBaseError):
            delete_extra_wiki_chunks(1, 3, client=client)

    def test_missing_page_has_application_error(self):
        with patch("corpdb.database.read_wiki_page.transaction_connection") as transaction:
            transaction.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = None
            with self.assertRaises(DatabaseError):
                read_wiki_page(999)


if __name__ == "__main__":
    unittest.main()
