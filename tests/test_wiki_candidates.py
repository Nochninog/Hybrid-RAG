"""Объединение результатов поиска и границы операции подбора Wiki."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.database.errors import DatabaseError
from backend.wiki.find_wiki_candidates import find_wiki_candidates


def chunk(uuid, page_id, position, distance=None):
    return SimpleNamespace(
        uuid=uuid, properties={"wiki_page_id": page_id, "position": position,
                               "text": f"text-{uuid}", "title": "Старое название"},
        vector={"qwen": [0.1, 0.2]}, metadata=SimpleNamespace(distance=distance),
    )


class WikiCandidatesTests(unittest.TestCase):
    def setUp(self):
        module = "corpdb.wiki.find_wiki_candidates"
        self.page = self.enterContext(patch(module + ".read_wiki_page", return_value=("Название из БД", "text")))
        self.factory = self.enterContext(patch(module + ".create_connection"))
        self.client = self.factory.return_value.__enter__.return_value
        self.read = self.enterContext(patch(module + ".read_wiki_chunks", return_value=[
            chunk("s0", 1, 0), chunk("s1", 1, 1),
        ]))
        self.search = self.enterContext(patch(module + ".search_wiki_chunks", return_value=[]))
        self.active = self.enterContext(patch(module + ".read_active_document_indexes", return_value=[]))
        self.document_search = self.enterContext(patch(module + ".search_document_chunks", return_value=[]))
        self.document_pages = self.enterContext(patch(module + ".read_wiki_pages_for_documents", return_value={}))

    def test_merges_pages_keeps_best_pair_and_distinct_evidence(self):
        self.search.side_effect = [
            [chunk("a", 2, 0, .4), chunk("b", 2, 1, .5), chunk("c", 3, 0, .2)],
            [chunk("a", 2, 0, .1), chunk("d", 2, 2, .3), chunk("self", 1, 0, 0)],
        ]
        result = find_wiki_candidates(1)
        self.assertEqual([x["page_id"] for x in result["candidates"]], [2, 3])
        best = result["candidates"][0]
        self.assertEqual(best["title"], "Название из БД")
        self.assertEqual([x["matched_chunk_uuid"] for x in best["evidence"]], ["a", "d"])
        self.assertEqual(best["evidence"][0]["source_chunk_uuid"], "s1")
        self.assertEqual(best["best_distance"], .1)
        self.assertEqual(result["stats"]["match_count"], 6)
        self.assertFalse(result["truncated"])
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.search.call_count, 2)
        for call in self.search.call_args_list:
            self.assertIs(call.kwargs["client"], self.client)
            self.assertEqual(call.kwargs["exclude_page_id"], 1)

    def test_limits_ties_and_truncation(self):
        self.search.side_effect = [[chunk("c", 3, 0, .2), chunk("b", 2, 0, .2)], []]
        result = find_wiki_candidates(1, hits_per_chunk=3, max_candidates=1, evidence_per_candidate=1)
        self.assertEqual(result["candidates"][0]["page_id"], 2)
        self.assertEqual(result["stats"]["unique_candidate_count"], 2)
        self.assertTrue(result["truncated"])
        self.assertEqual(self.search.call_args.kwargs["limit"], 3)

    def test_no_matches_is_successful_empty_result(self):
        result = find_wiki_candidates(1)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["stats"]["search_count"], 2)
        self.assertFalse(result["truncated"])

    def test_missing_page_and_missing_index_are_distinct(self):
        self.page.side_effect = DatabaseError("missing")
        with self.assertRaises(DatabaseError):
            find_wiki_candidates(1)
        self.factory.assert_not_called()
        self.page.side_effect = None
        self.read.return_value = []
        with self.assertRaisesRegex(ValueError, "проиндексируйте"):
            find_wiki_candidates(1)
        self.search.assert_not_called()

    def test_bad_limits_fail_before_io(self):
        for name in ("hits_per_chunk", "max_candidates", "evidence_per_candidate"):
            for value in (0, -1, True, 1.5):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    find_wiki_candidates(1, **{name: value})
        self.page.assert_not_called()

    def test_search_failure_and_invalid_distance_fail_without_partial_result(self):
        self.search.side_effect = [[], RuntimeError("failed")]
        with self.assertRaises(RuntimeError):
            find_wiki_candidates(1)
        self.search.side_effect = None
        self.search.return_value = [chunk("bad", 2, 0, float("nan"))]
        with self.assertRaisesRegex(ValueError, "расстояния"):
            find_wiki_candidates(1)

    def test_missing_vector_stops_search(self):
        self.read.return_value[0].vector = {}
        with self.assertRaisesRegex(ValueError, "вектора qwen"):
            find_wiki_candidates(1)
        self.search.assert_not_called()

    def test_two_channels_shared_document_and_per_channel_evidence(self):
        self.active.return_value = [(10, "key", "run")]
        self.search.side_effect = [[chunk("same", 2, 0, .3)], []]
        first = chunk("same", 0, 0, .2)
        first.properties.update(document_id=10, storage_key="key", index_run_id="run")
        better = chunk("same", 0, 0, .1)
        better.properties.update(document_id=10, storage_key="key", index_run_id="run")
        self.document_search.side_effect = [[first], [better]]
        self.document_pages.return_value = {10: [1, 2, 3]}
        result = find_wiki_candidates(1, evidence_per_candidate=1)
        self.assertEqual([x["page_id"] for x in result["candidates"]], [2, 3])
        candidate = result["candidates"][0]
        self.assertEqual(candidate["channels"], ["wiki", "document"])
        self.assertEqual(len(candidate["evidence"]), 2)
        evidence = candidate["evidence"][0]
        self.assertEqual(evidence["source_chunk_uuid"], "s1")
        self.assertEqual(evidence["document_id"], 10)
        self.assertEqual(evidence["index_run_id"], "run")
        self.assertEqual(result["stats"]["search_count"], 4)
        self.assertEqual(result["stats"]["document_match_count"], 2)
        self.document_pages.assert_called_once_with([10])
        self.document_search.assert_called_with([.1, .2], active_documents=self.active.return_value,
                                                client=self.client, limit=10)

    def test_document_without_wiki_does_not_create_candidate(self):
        self.active.return_value = [(10, "key", "run")]
        found = chunk("d", 0, 0, .2)
        found.properties.update(document_id=10, storage_key="key", index_run_id="run")
        self.document_search.return_value = [found]
        result = find_wiki_candidates(1)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["stats"]["document_match_count"], 2)

    def test_document_failure_is_not_a_partial_success(self):
        self.active.return_value = [(10, "key", "run")]
        self.document_search.side_effect = RuntimeError("failed")
        with self.assertRaises(RuntimeError):
            find_wiki_candidates(1)

    def test_no_active_documents_skips_document_search(self):
        find_wiki_candidates(1)
        self.document_search.assert_not_called()
