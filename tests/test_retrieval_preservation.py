"""Сохранение найденного при blacklist и при повторном поиске оригиналов."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.llm.gigachat import IncompleteGenerationError
from backend.answering.budget import AnswerBudget
from backend.retrieval.search import find_document_candidates
from backend.workflows.explore import answer_question, explore_question


def chunk(uuid="initial", *, run="run"):
    return {"document_id": 1, "storage_key": "key", "index_run_id": run,
            "matched_chunk_uuid": uuid, "matched_position": 0,
            "text": "Исходный фрагмент", "distance": .2}


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.initial = chunk()
        module = "corpdb.workflows.explore"
        self.search = self.enterContext(patch(module + ".search_question_with_vector", return_value=(
            {"document_chunks": [self.initial], "start_pages": [{"page_id": 10}]}, [.1],
        )))
        self.links = self.enterContext(patch(module + ".read_wiki_links", return_value=[(20, "Wiki", "Связь")]))
        self.generate = self.enterContext(patch(module + ".generate_text"))

    def test_first_blacklist_preserves_start_and_continues_to_answer(self):
        self.generate.side_effect = IncompleteGenerationError("blacklist")
        with (
            patch("corpdb.workflows.explore.find_document_candidates", return_value=[self.initial]) as candidates,
            patch("corpdb.workflows.explore.select_evidence", return_value=([self.initial], [])) as select,
            patch("corpdb.workflows.explore.generate_answer", return_value={"answer": "Ответ", "sources": []}) as answer,
        ):
            result = answer_question("Вопрос")
        candidates.assert_called_once_with([10], [.1], {}, initial_chunks=[self.initial])
        select.assert_called_once()
        answer.assert_called_once()
        self.assertEqual(result["page_ids"], [10])
        self.assertEqual(result["explore_status"], "interrupted")
        self.assertEqual(result["explore_error"], {"finish_reason": "blacklist", "source_page_id": 10, "depth": 0})
        self.assertEqual(result["trace"][0]["selected_page_ids"], [])
        self.assertEqual(result["trace"][0]["error"], result["explore_error"])

    def test_other_generation_and_code_errors_propagate(self):
        for error in (IncompleteGenerationError("length"), ValueError("Некорректные данные"), RuntimeError("bug")):
            with self.subTest(error=str(error)):
                self.generate.side_effect = error
                with self.assertRaises(type(error)):
                    explore_question("Вопрос")

    def test_success_has_no_interruption(self):
        self.generate.return_value = '{"targets": []}'
        result = explore_question("Вопрос")
        self.assertEqual(result["explore_status"], "completed")
        self.assertIsNone(result["explore_error"])

    def test_answer_budget_and_budget_gaps_pass_through_graph_independently_of_search_limit(self):
        self.generate.return_value = '{"targets": []}'
        budget = AnswerBudget(max_input_tokens=1000)
        def select(question, chunks, *, budget, selection_metadata):
            selection_metadata.update(budget_missing_parts=["Совместные опоры"], status="budget_limited")
            return [], ["Нет сведений"]
        with (
            patch("corpdb.workflows.explore.find_document_candidates", return_value=[self.initial]),
            patch("corpdb.workflows.explore.select_evidence", side_effect=select) as selection,
            patch("corpdb.workflows.explore.generate_answer", return_value={"answer": "Бюджет", "sources": []}) as answer,
        ):
            result = answer_question("Q", limit=2, answer_budget=budget)
        self.assertIs(selection.call_args.kwargs["budget"], budget)
        self.assertNotIn("limit", selection.call_args.kwargs)
        self.assertIs(answer.call_args.kwargs["budget"], budget)
        self.assertEqual(answer.call_args.kwargs["budget_missing_parts"], ["Совместные опоры"])
        self.assertEqual(result["budget_missing_parts"], ["Совместные опоры"])
        self.assertEqual(result["missing_parts"], ["Нет сведений"])

    def test_replay_all_five_saved_blacklists_preserves_prior_discoveries(self):
        root = Path(__file__).resolve().parents[1] / "data/enterprise_rag_sample/answer_compare_20261111"
        graph = json.loads((root.parent / "wiki_links_20261111/links.json").read_text(encoding="utf-8"))
        for qid in ("qst_0475", "qst_0479", "qst_0497", "qst_0366", "qst_0192"):
            with self.subTest(question=qid):
                saved = json.loads((root / f"{qid}-wiki.json").read_text(encoding="utf-8"))
                calls = [c for c in saved["calls"] if c["stage"] == "explore"]
                self.assertIn("blacklist", saved["error"]["detail"])
                self.search.return_value = ({"document_chunks": saved["document_chunks"],
                                             "start_pages": saved["start_pages"]}, [.1])
                self.links.side_effect = lambda page: [
                    (c["target_page_id"], "Wiki", c["explanation"])
                    for c in graph if c["source_page_id"] == page
                ]
                self.generate.side_effect = [
                    c["output"] if "output" in c else IncompleteGenerationError("blacklist") for c in calls
                ]
                expected = [p["page_id"] for p in saved["start_pages"]]
                for c in calls:
                    if "output" in c:
                        for target in json.loads(c["output"])["targets"]:
                            if target["target_page_id"] not in expected:
                                expected.append(target["target_page_id"])
                with (
                    patch("corpdb.workflows.explore.find_document_candidates", return_value=[]) as candidates,
                    patch("corpdb.workflows.explore.select_evidence", return_value=([], [])) as select,
                ):
                    result = answer_question(saved["question"])
                self.assertEqual(result["page_ids"], expected)
                self.assertEqual(result["explore_status"], "interrupted")
                self.assertEqual(result["explore_error"]["source_page_id"], calls[-1]["input"]["source_page_id"])
                self.assertEqual(candidates.call_args.args[0], expected)
                select.assert_called_once()
                if qid == "qst_0366":
                    self.assertTrue({110, 144, 154} <= set(result["page_ids"]))


class CandidatePreservationTests(unittest.TestCase):
    def setUp(self):
        module = "corpdb.retrieval.search"
        self.active = self.enterContext(patch(module + ".read_active_document_indexes", return_value=[(1, "key", "run")]))
        self.pages = self.enterContext(patch(module + ".read_documents_for_wiki_pages", return_value={1: [10, 20]}))
        self.embed = self.enterContext(patch(module + ".embed_texts", return_value=[[.2]]))
        self.enterContext(patch(module + ".create_connection"))
        self.query = self.enterContext(patch(module + ".search_document_chunks"))

    def test_union_keeps_initial_only_and_both_origins_without_mutation(self):
        initial = chunk()
        matches = [SimpleNamespace(uuid=uuid, properties={"document_id": 1, "storage_key": "key",
                   "index_run_id": "run", "position": 0, "text": "Фрагмент"}, metadata=SimpleNamespace(distance=.1))
                   for uuid in ("initial", "wiki")]
        self.query.return_value = matches
        extra = chunk("initial-only")
        result = find_document_candidates([10, 20], [.1], {20: "Уточнение"}, initial_chunks=[initial, initial, extra])
        self.assertEqual([c["matched_chunk_uuid"] for c in result], ["initial", "initial-only", "wiki"])
        self.assertEqual(result[0]["retrieval_origins"], ["initial_search", "wiki_search"])
        self.assertEqual(result[1]["retrieval_origins"], ["initial_search"])
        self.assertEqual(result[2]["retrieval_origins"], ["wiki_search"])
        self.assertEqual(result[0]["text"], initial["text"])
        self.assertEqual(result[0]["wiki_page_ids"], [10, 20])
        self.assertNotIn("retrieval_origins", initial)
        self.assertEqual([c.kwargs["limit"] for c in self.query.call_args_list], [10, 10])

    def test_no_wiki_retains_initial_without_vector_search(self):
        self.pages.return_value = {}
        result = find_document_candidates([], [.1], {}, initial_chunks=[chunk()])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["wiki_page_ids"], [])
        self.query.assert_not_called()
        self.embed.assert_not_called()

    def test_replaced_or_deactivated_initial_version_is_excluded(self):
        self.pages.return_value = {}
        for active in ([], [(1, "new-key", "run")], [(1, "key", "new-run")]):
            with self.subTest(active=active):
                self.active.return_value = active
                self.assertEqual(find_document_candidates([], [.1], {}, initial_chunks=[chunk()]), [])

    def test_configurable_per_page_limit_is_validated_and_forwarded(self):
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, "per_page_limit"):
                    find_document_candidates([10], [.1], {}, per_page_limit=limit)
        self.active.assert_not_called()
        self.query.return_value = []
        for limit in (3, 5, 10):
            with self.subTest(limit=limit):
                find_document_candidates([10], [.1], {}, per_page_limit=limit)
                self.assertEqual(self.query.call_args.kwargs["limit"], limit)

    def test_qst_0133_threshold_fragment_reaches_selection(self):
        root = Path(__file__).resolve().parents[1] / "data/enterprise_rag_sample/answer_compare_20261111"
        saved = json.loads((root / "qst_0133-wiki.json").read_text(encoding="utf-8"))
        initial = [{**c, "storage_key": "key", "index_run_id": "run"} for c in saved["document_chunks"]]
        self.active.return_value = [(c["document_id"], "key", "run") for c in initial]
        self.pages.return_value = {}
        candidates = find_document_candidates([], [.1], {}, initial_chunks=initial)
        expected = next(c for c in initial if c["document_id"] == 153 and c["matched_position"] == 1)
        self.assertEqual(sum(c["matched_chunk_uuid"] == expected["matched_chunk_uuid"] for c in candidates), 1)
        with (
            patch("corpdb.workflows.explore.search_question_with_vector", return_value=({
                "document_chunks": initial, "start_pages": [],
            }, [.1])),
            patch("corpdb.workflows.explore.select_evidence", return_value=([], [])) as select,
        ):
            result = answer_question(saved["question"])
        self.assertIn(expected["matched_chunk_uuid"], [c["matched_chunk_uuid"] for c in select.call_args.args[1]])
        self.assertEqual(result["candidates"], candidates)


if __name__ == "__main__":
    unittest.main()
