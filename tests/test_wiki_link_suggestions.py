import unittest
from unittest.mock import call, patch

from backend.wiki.suggest_wiki_links import suggest_wiki_links


MODULE = "corpdb.wiki.suggest_wiki_links"


def evaluation(target, forward, backward):
    return {
        "page_a_id": 1, "page_b_id": target,
        "a_to_b": {"create": forward, "explanation": f"1 to {target}"},
        "b_to_a": {"create": backward, "explanation": f"{target} to 1"},
    }


class WikiLinkSuggestionTests(unittest.TestCase):
    def setUp(self):
        self.find = self.enterContext(patch(MODULE + ".find_wiki_candidates"))
        self.evaluate = self.enterContext(patch(MODULE + ".evaluate_wiki_pair"))
        self.find.return_value = {
            "source_page_id": 1,
            "candidates": [{"page_id": i, "evidence": ["search evidence"]} for i in (4, 5, 3, 8)],
            "truncated": True,
            "stats": {"returned_candidate_count": 4},
        }

    def test_directions_rejections_order_and_limits(self):
        self.evaluate.side_effect = [evaluation(4, True, False), evaluation(5, False, True),
                                     evaluation(3, True, True), evaluation(8, False, False)]
        result = suggest_wiki_links(1, hits_per_chunk=3, max_candidates=4,
                                    evidence_per_candidate=1, max_input_chars=9000)
        self.find.assert_called_once_with(1, hits_per_chunk=3, max_candidates=4, evidence_per_candidate=1)
        self.assertEqual(self.evaluate.call_args_list,
                         [call(1, i, max_input_chars=9000) for i in (4, 5, 3, 8)])
        self.assertEqual(result["links"], [
            {"source_page_id": a, "target_page_id": b, "explanation": f"{a} to {b}"}
            for a, b in ((1, 4), (5, 1), (1, 3), (3, 1))
        ])
        self.assertEqual(len(result["evaluations"]), 4)
        self.assertFalse(result["evaluations"][-1]["a_to_b"]["create"])
        self.assertIs(result["retrieval"], self.find.return_value)

    def test_empty_candidates_skip_model(self):
        self.find.return_value["candidates"] = []
        result = suggest_wiki_links(1)
        self.assertEqual(result["links"], [])
        self.assertEqual(result["evaluations"], [])
        self.evaluate.assert_not_called()

    def test_search_error_stops_before_evaluation(self):
        self.find.side_effect = RuntimeError("search failed")
        with self.assertRaisesRegex(RuntimeError, "search failed"):
            suggest_wiki_links(1)
        self.evaluate.assert_not_called()

    def test_pair_error_stops_without_partial_success(self):
        self.evaluate.side_effect = [evaluation(4, True, True), ValueError("invalid response")]
        with self.assertRaisesRegex(ValueError, "invalid response"):
            suggest_wiki_links(1)
        self.assertEqual(self.evaluate.call_count, 2)

    def test_invalid_input_before_search(self):
        for page_id, limit in ((True, 100), (0, 100), ("1", 100), (1, 0), (1, True)):
            with self.subTest(page_id=page_id, limit=limit), self.assertRaises(ValueError):
                suggest_wiki_links(page_id, max_input_chars=limit)
        self.find.assert_not_called()
        self.evaluate.assert_not_called()
