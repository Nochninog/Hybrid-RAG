"""Поиск по одному вектору вопроса и объединение Wiki из двух каналов."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from weaviate.classes.query import Filter
from weaviate.collections.filters import _FilterToGRPC

from backend.answering.answer import NO_ANSWER, generate_answer, select_evidence
from backend.retrieval.search import search_question
from backend.workflows.explore import answer_question


def match(uuid, id_property, owner_id, distance):
    return SimpleNamespace(
        uuid=uuid,
        properties={id_property: owner_id, "position": 0, "text": f"Текст {uuid}",
                    "storage_key": "initial" if owner_id == 70 else "current" if owner_id == 68 else "key",
                    "index_run_id": "run-70" if owner_id == 70 else "new-run" if owner_id == 68 else "run"},
        metadata=SimpleNamespace(distance=distance),
    )


class SearchQuestionTests(unittest.TestCase):
    def setUp(self):
        self.counter = self.enterContext(patch("corpdb.answering.answer.count_message_tokens", return_value=100))
        module = "corpdb.retrieval.search"
        self.vector = [.1, .2]
        self.embed = self.enterContext(patch(module + ".embed_texts", return_value=[self.vector]))
        self.active = self.enterContext(patch(
            module + ".read_active_document_indexes", return_value=[(1, "key", "run")],
        ))
        self.pages = self.enterContext(patch(module + ".read_wiki_pages_for_documents", return_value={}))
        factory = self.enterContext(patch(module + ".create_connection"))
        client = factory.return_value.__enter__.return_value
        collections = {"DocumentChunk": Mock(), "WikiChunk": Mock()}
        client.collections.get.side_effect = collections.__getitem__
        self.document_query = collections["DocumentChunk"].query.near_vector
        self.wiki_query = collections["WikiChunk"].query.near_vector

    def test_merge_keeps_both_channels_and_original_chunks(self):
        self.document_query.return_value.objects = [match("d1", "document_id", 1, .2)]
        self.wiki_query.return_value.objects = [
            match("w1", "wiki_page_id", 11, .3),
            match("w2", "wiki_page_id", 12, .1),
        ]
        self.pages.return_value = {1: [11, 13]}

        result = search_question("  Вопрос  ", limit=3)

        self.embed.assert_called_once_with(["Вопрос"])
        self.pages.assert_called_once_with([1])
        self.assertIs(self.document_query.call_args.kwargs["near_vector"], self.vector)
        self.assertIs(self.wiki_query.call_args.kwargs["near_vector"], self.vector)
        self.assertEqual(self.document_query.call_args.kwargs["limit"], 3)
        self.assertEqual(self.wiki_query.call_args.kwargs["limit"], 3)
        self.assertIsNone(self.wiki_query.call_args.kwargs["filters"])
        self.assertEqual([page["page_id"] for page in result["start_pages"]], [12, 11, 13])
        self.assertEqual(result["start_pages"][1]["channels"], ["document", "wiki"])
        self.assertEqual([item["matched_chunk_uuid"] for item in result["start_pages"][1]["evidence"]], ["d1", "w1"])
        self.assertEqual(result["document_chunks"][0]["text"], "Текст d1")

    def test_document_without_wiki_is_retained(self):
        self.document_query.return_value.objects = [match("d1", "document_id", 1, .2)]
        self.wiki_query.return_value.objects = []

        result = search_question("Вопрос")

        self.assertEqual(result["start_pages"], [])
        self.assertEqual([chunk["document_id"] for chunk in result["document_chunks"]], [1])

    def test_empty_question_stops_before_io(self):
        with self.assertRaisesRegex(ValueError, "пустым"):
            search_question("  ")
        self.active.assert_not_called()
        self.embed.assert_not_called()

    def test_answer_searches_each_wiki_and_selects_each_fragment(self):
        self.active.side_effect = [
            [(70, "initial", "run-70"), (68, "old", "old-run"), (99, "other", "run-99")],
            [(70, "initial", "run-70"), (68, "current", "new-run"), (99, "other", "run-99")],
        ]
        first = match("d70", "document_id", 70, .2)
        second = match("d68", "document_id", 68, .3)
        extra = match("d68-extra", "document_id", 68, .4)
        self.document_query.side_effect = [
            SimpleNamespace(objects=matches) for matches in ([first], [first, second], [second, extra])
        ]
        self.embed.side_effect = [[self.vector], [[.3, .4]]]
        self.wiki_query.return_value.objects = [match("w34", "wiki_page_id", 34, .1)]
        with (
            patch("corpdb.workflows.explore.read_wiki_links", return_value=[(32, "Wiki 32", "Связь")]),
            patch("corpdb.workflows.explore.generate_text", return_value=json.dumps({"targets": [
                {"target_page_id": 32, "search_query": "Масса"},
            ]})),
            patch("corpdb.database.read_documents_for_wiki_pages.transaction_connection") as database,
            patch("corpdb.answering.answer.generate_text", side_effect=[
                json.dumps({"contains_answer": True}), json.dumps({"contains_answer": True}),
                json.dumps({"contains_answer": False}), "Ответ [1] [2]."]) as model,
        ):
            cursor = database.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchall.return_value = [(68, 32), (68, 34), (70, 34)]
            result = answer_question("Вопрос", limit=2, max_expansions=1)

        cursor.execute.assert_called_once()
        self.assertIn("WHERE wiki_page_id = ANY(%s)", cursor.execute.call_args.args[0])
        self.assertEqual(cursor.execute.call_args.args[1], ([34, 32],))
        self.assertEqual(self.embed.call_args_list, [call(["Вопрос"]), call(["Масса"])])
        self.assertEqual(self.document_query.call_count, 3)
        self.assertIs(self.document_query.call_args_list[1].kwargs["near_vector"], self.vector)
        query = self.document_query.call_args.kwargs
        self.assertEqual(query["near_vector"], [.3, .4])
        self.assertEqual(query["limit"], 10)
        expected = Filter.any_of([
            Filter.by_property("document_id").equal(doc)
            & Filter.by_property("storage_key").equal(key)
            & Filter.by_property("index_run_id").equal(run)
            for doc, key, run in [(68, "current", "new-run")]
        ])
        self.assertEqual(_FilterToGRPC.convert(query["filters"]), _FilterToGRPC.convert(expected))
        self.assertEqual(result["page_ids"], [34, 32])
        self.assertEqual(result["document_chunks"][0]["document_id"], 70)
        self.assertEqual([chunk["document_id"] for chunk in result["selected_chunks"]], [70, 68])
        self.assertEqual(result["missing_parts"], [])
        self.assertEqual(result["answer"], "Ответ [1] [2].")
        self.assertEqual(result["sources"][1], {
            "source_id": 2, "document_id": 68, "matched_chunk_uuid": "d68",
            "matched_position": 0, "wiki_page_ids": [32, 34],
        })
        for request, text in zip(model.call_args_list[:3],
                                 ["Текст d70", "Текст d68", "Текст d68-extra"], strict=True):
            self.assertEqual(json.loads(request.args[0][1]["content"]),
                             {"question": "Вопрос", "fragment": text})
        messages, = model.call_args.args
        self.assertEqual(json.loads(messages[1]["content"]), {
            "question": "Вопрос", "missing_parts": [], "budget_missing_parts": [], "fragments": [
                {"source_id": 1, "text": "Текст d70"}, {"source_id": 2, "text": "Текст d68"},
            ],
        })

    def test_answer_without_wiki_passes_initial_hits_to_selection(self):
        self.document_query.return_value.objects = [match("d1", "document_id", 1, .2)]
        self.wiki_query.return_value.objects = []
        with (
            patch("corpdb.workflows.explore.read_wiki_links") as links,
            patch("corpdb.answering.answer.generate_text", side_effect=[
                json.dumps({"contains_answer": True}), "Ответ [1]."]) as model,
        ):
            result = answer_question("Вопрос")

        links.assert_not_called()
        self.assertEqual(model.call_count, 2)
        self.document_query.assert_called_once()
        self.assertEqual(result["document_chunks"][0]["document_id"], 1)
        self.assertEqual(len(result["selected_chunks"]), 1)
        self.assertEqual(result["candidates"][0]["wiki_page_ids"], [])
        self.assertEqual(result["candidates"][0]["retrieval_origins"], ["initial_search"])
        self.assertEqual(result["answer"], "Ответ [1].")

    def test_evidence_keeps_shared_chunks_without_old_char_cap(self):
        chunks = [{"document_id": 1, "text": char * size} for char, size in zip("abcd", [5000, 6000, 6000, 3000])]
        with patch("corpdb.answering.answer.generate_text", return_value=json.dumps({"contains_answer": True})):
            selected, missing = select_evidence("Вопрос", chunks)

        self.assertEqual(selected, [chunks[0], chunks[1], chunks[2], chunks[3]])
        self.assertEqual(missing, [])

    def test_answer_collects_single_and_grouped_citations(self):
        chunks = [
            {"document_id": i, "matched_chunk_uuid": str(i), "matched_position": 0,
             "wiki_page_ids": [], "text": "Текст"}
            for i in range(1, 4)
        ]
        with patch("corpdb.answering.answer.generate_text", return_value="Ответ [2, 3] [2]."):
            result = generate_answer("Вопрос", chunks)

        self.assertEqual([source["source_id"] for source in result["sources"]], [2, 3])
        self.assertEqual([source["matched_chunk_uuid"] for source in result["sources"]], ["2", "3"])

        with patch("corpdb.answering.answer.generate_text", return_value="Ответ [1] [2, 4]."):
            with self.assertRaisesRegex(ValueError, "некорректные ссылки"):
                generate_answer("Вопрос", chunks)
