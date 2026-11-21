"""Проверки обхода Wiki через LangGraph с подменой внешних вызовов."""

import json
import unittest
from unittest.mock import call, patch

from backend.workflows.explore import explore_question


class ExploreTests(unittest.TestCase):
    def setUp(self):
        module = "corpdb.workflows.explore"
        self.search = self.enterContext(patch(module + ".search_question_with_vector", return_value=({
            "document_chunks": [{"document_id": 10}],
            "start_pages": [{"page_id": 1}, {"page_id": 2}],
        }, [.1, .2])))
        self.read_links = self.enterContext(patch(module + ".read_wiki_links"))
        self.generate = self.enterContext(patch(module + ".generate_text"))

    def test_breadth_first_with_cycles_and_depth_limit(self):
        self.read_links.side_effect = {
            1: [(2, "Wiki 2", "Уже в очереди"), (3, "Wiki 3", "Контекст перехода")],
            2: [(3, "Wiki 3", "Уже найдена"), (5, "Wiki 5", "Другая тема")],
            3: [(1, "Wiki 1", "Цикл"), (4, "Wiki 4", "Второй переход")],
        }.__getitem__
        self.generate.side_effect = [
            '{"targets": [{"target_page_id": 3, "search_query": "Масса"}, '
            '{"target_page_id": 3, "search_query": "Повтор"}]}',
            '{"targets": []}',
            '{"targets": [{"target_page_id": 4, "search_query": "Радиус"}]}',
        ]

        result = explore_question(" Вопрос ", limit=5)

        self.search.assert_called_once_with("Вопрос", limit=5)
        self.assertEqual(self.read_links.call_args_list, [call(1), call(2), call(3)])
        self.assertEqual(result["document_chunks"], [{"document_id": 10}])
        self.assertEqual(result["start_pages"], [{"page_id": 1}, {"page_id": 2}])
        self.assertEqual(result["page_ids"], [1, 2, 3, 4])
        self.assertEqual([step["depth"] for step in result["trace"]], [0, 0, 1])
        first_step = result["trace"][0]
        self.assertEqual(first_step["selected_page_ids"], [3])
        self.assertEqual(first_step["search_queries"], {3: "Масса"})
        self.assertEqual(first_step["candidates"], [
            {"target_page_id": 3, "title": "Wiki 3", "explanation": "Контекст перехода"},
        ])
        payload = json.loads(self.generate.call_args_list[0].args[0][1]["content"])
        self.assertEqual(payload["candidates"], first_step["candidates"])

    def test_budget_stops_after_page_without_candidates(self):
        self.read_links.return_value = []

        result = explore_question("Вопрос", max_expansions=1)

        self.read_links.assert_called_once_with(1)
        self.generate.assert_not_called()
        self.assertEqual(result["page_ids"], [1, 2])
        self.assertEqual(len(result["trace"]), 1)

    def test_empty_start_pages_skip_explore(self):
        self.search.return_value[0]["start_pages"] = []

        result = explore_question("Вопрос")

        self.read_links.assert_not_called()
        self.generate.assert_not_called()
        self.assertEqual(result["page_ids"], [])
        self.assertEqual(result["trace"], [])
        self.assertEqual(result["document_chunks"], [{"document_id": 10}])

    def test_skips_known_and_unknown_targets_and_keeps_valid_transition(self):
        self.read_links.side_effect = {1: [(3, "Wiki 3", "Связь")], 2: [], 3: []}.__getitem__
        self.generate.return_value = json.dumps({"targets": [
            {"target_page_id": 1, "search_query": "Текущая"},
            {"target_page_id": 2, "search_query": "Уже в очереди"},
            {"target_page_id": 4, "search_query": "Посторонняя"},
            {"target_page_id": 3, "search_query": "Нужные сведения"},
        ]})

        result = explore_question("Вопрос")

        self.assertEqual(self.read_links.call_args_list, [call(1), call(2), call(3)])
        self.assertEqual(result["page_ids"], [1, 2, 3])
        self.assertEqual(result["trace"][0]["search_queries"], {3: "Нужные сведения"})
        self.assertEqual(result["trace"][0]["ignored_unknown_page_ids"], [4])

    def test_rejects_ids_with_wrong_type(self):
        self.read_links.return_value = [(3, "Wiki 3", "Контекст перехода")]

        for invalid_id in (True, "3"):
            with self.subTest(invalid_id=invalid_id):
                self.generate.return_value = json.dumps({"targets": [
                    {"target_page_id": invalid_id, "search_query": "Масса"},
                ]})
                with self.assertRaisesRegex(ValueError, "некорректный ID"):
                    explore_question("Вопрос")
