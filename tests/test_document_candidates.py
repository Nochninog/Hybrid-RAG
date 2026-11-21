"""Фильтрация активных наборов до top-k и пакетное чтение Wiki по источникам."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from weaviate.classes.query import Filter
from weaviate.collections.filters import _FilterToGRPC

from backend.database.read_active_document_indexes import read_active_document_indexes
from backend.database.read_wiki_pages_for_documents import read_wiki_pages_for_documents
from backend.indexes.search_document_chunks import search_document_chunks


class DocumentSearchTests(unittest.TestCase):
    def test_complete_state_triples_are_filtered_before_limit(self):
        client = Mock()
        query = client.collections.get.return_value.query
        objects = [object()]
        query.near_vector.return_value = SimpleNamespace(objects=objects)
        states = [(1, "new-key", "run-1"), (2, "other-key", "run-2")]
        result = search_document_chunks([.1, .2], active_documents=states, client=client, limit=3)
        self.assertIs(result, objects)
        kwargs = query.near_vector.call_args.kwargs
        expected = Filter.any_of([
            Filter.by_property("document_id").equal(doc)
            & Filter.by_property("storage_key").equal(key)
            & Filter.by_property("index_run_id").equal(run)
            for doc, key, run in states
        ])
        self.assertEqual(_FilterToGRPC.convert(kwargs["filters"]), _FilterToGRPC.convert(expected))
        self.assertEqual(kwargs["limit"], 3)
        self.assertEqual(kwargs["target_vector"], "qwen")
        self.assertTrue(kwargs["return_metadata"].distance)
        self.assertFalse(kwargs["include_vector"])
        client.collections.get.assert_called_once_with("DocumentChunk")

    def test_empty_states_do_not_query_and_invalid_limits_fail(self):
        client = Mock()
        self.assertEqual(search_document_chunks([.1], active_documents=[], client=client), [])
        for limit in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                search_document_chunks([.1], active_documents=[], client=client, limit=limit)
        client.collections.get.assert_not_called()

    def test_query_error_propagates(self):
        client = Mock()
        client.collections.get.return_value.query.near_vector.side_effect = RuntimeError("failed")
        with self.assertRaises(RuntimeError):
            search_document_chunks([.1], active_documents=[(1, "key", "run")], client=client)


class DocumentWikiReadTests(unittest.TestCase):
    def test_many_to_many_mapping_and_unique_input(self):
        with patch("corpdb.database.read_wiki_pages_for_documents.transaction_connection") as factory:
            cursor = factory.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchall.return_value = [(10, 1), (10, 2), (11, 2)]
            self.assertEqual(read_wiki_pages_for_documents([10, 11, 10, 12]), {10: [1, 2], 11: [2]})
            self.assertEqual(cursor.execute.call_args.args[1], ([10, 11, 12],))

    def test_empty_ids_skip_database(self):
        with patch("corpdb.database.read_wiki_pages_for_documents.transaction_connection") as factory:
            self.assertEqual(read_wiki_pages_for_documents([]), {})
            factory.assert_not_called()

    def test_active_state_reads_only_activated_and_serializes_uuid(self):
        with patch("corpdb.database.read_active_document_indexes.transaction_connection") as factory:
            cursor = factory.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            run = UUID(int=1)
            cursor.fetchall.return_value = [(10, "key", run)]
            self.assertEqual(read_active_document_indexes(), [(10, "key", str(run))])
            self.assertIn("active_index_run_id IS NOT NULL", cursor.execute.call_args.args[0])
