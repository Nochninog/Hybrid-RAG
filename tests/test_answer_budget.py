"""Пофрагментный отбор и границы полного входа Answer."""

import json
import unittest
from unittest.mock import patch

from backend.answering.answer import (
    BUDGET_NO_ANSWER, NO_ANSWER, answer_messages, generate_answer, select_evidence,
)
from backend.answering.budget import AnswerBudget, InputBudgetExceeded


def output(value):
    return json.dumps({"contains_answer": value})


def chunk(i, text="evidence"):
    return {"document_id": i, "text": text, "matched_chunk_uuid": str(i),
            "matched_position": 0, "wiki_page_ids": []}


class AnswerBudgetTests(unittest.TestCase):
    def setUp(self):
        # Детерминированный счётчик тестовых токенов, НЕ производственный tokenizer.
        # Полный envelope учитывает и вопрос, и обе причины пробелов.
        self.budget = AnswerBudget(max_input_tokens=100, max_output_tokens=30,
                                   context_tokens=10_000, safety_tokens=10)
        def count(messages, *, response_schema=None):
            if response_schema:
                return 500
            body = json.loads(messages[1]["content"])
            return (20 + len(body["question"]) + sum(len(c["text"]) for c in body["fragments"])
                    + sum(len(s) for key in ("missing_parts", "budget_missing_parts") for s in body[key]))
        self.counter = self.enterContext(patch("corpdb.answering.answer.count_message_tokens", side_effect=count))
        self.model = self.enterContext(patch("corpdb.answering.answer.generate_text"))

    def select(self, chunks, *responses):
        self.model.side_effect = list(responses)
        details = {}
        selected, missing = select_evidence("Q", chunks, budget=self.budget, selection_metadata=details)
        return selected, missing, details

    def test_more_than_ten_and_long_chunk_are_not_filtered_by_old_limits(self):
        self.counter.side_effect = None
        self.counter.return_value = 10
        chunks = [chunk(i) for i in range(12)] + [chunk(99, "x" * 17000)]
        selected, missing, details = self.select(chunks, *[output(True)] * len(chunks))
        self.assertEqual(selected, chunks)
        self.assertEqual(missing, [])
        self.assertEqual(len(details["attempts"]), len(chunks))

    def test_requests_contain_one_fragment_and_question_only(self):
        chunks = [chunk(1, "first part"), chunk(1, "second part"), chunk(3, "unrelated")]
        selected, missing, details = self.select(chunks, output(True), output(True), output(False))
        self.assertEqual(selected, chunks[:2])
        self.assertEqual(missing, [])
        self.assertEqual(details["relevant_ids"], [1, 2])
        for candidate, request in zip(chunks, self.model.call_args_list, strict=True):
            self.assertEqual(json.loads(request.args[0][1]["content"]),
                             {"question": "Q", "fragment": candidate["text"]})
            self.assertEqual(request.kwargs["max_tokens"], 30)

    def test_budget_preserves_whole_chunks_and_records_omissions(self):
        chunks = [chunk(1, "x" * 90), chunk(2, "small")]
        selected, missing, details = self.select(chunks, output(True), output(True))
        self.assertEqual(selected, [chunks[1]])
        self.assertEqual(missing, [])
        self.assertEqual(details["budget_dropped_ids"], [1])
        self.assertEqual(details["status"], "budget_limited")
        self.assertTrue(details["budget_missing_parts"])
        self.assertLessEqual(details["input_tokens"], self.budget.max_input_tokens)
        self.assertEqual(self.model.call_count, 2)

    def test_total_budget_loss_is_not_absence_of_evidence(self):
        selected, missing, details = self.select([chunk(1, "x" * 90)], output(True))
        self.assertEqual((selected, missing), ([], []))
        self.assertEqual(details["no_evidence_parts"], [])
        self.assertEqual(generate_answer("Q", selected,
                         budget_missing_parts=details["budget_missing_parts"])["answer"], BUDGET_NO_ANSWER)

    def test_true_missing_evidence_does_not_retry(self):
        selected, missing, details = self.select([chunk(1)], output(False))
        self.assertEqual((selected, missing), ([], ["Q"]))
        self.assertEqual(details["budget_missing_parts"], [])
        self.assertEqual(self.model.call_count, 1)
        self.assertEqual(generate_answer("Q", [], missing_parts=missing)["answer"], NO_ANSWER)

    def test_empty_fragments_do_not_call_model_and_keep_original_ids(self):
        chunks = [chunk(1, " "), chunk(2, "evidence")]
        selected, _, details = self.select(chunks, output(True))
        self.assertEqual(selected, chunks[1:])
        self.assertEqual(details["selected_ids"], [2])
        self.assertEqual(self.model.call_count, 1)
        self.model.reset_mock()
        selected, missing, _ = self.select([chunk(1, " ")])
        self.assertEqual((selected, missing), ([], ["Q"]))
        self.model.assert_not_called()

    def test_malformed_decisions_fail_without_silent_rejection(self):
        for reply in ('true', '{}', '{"contains_answer": "false"}',
                      '{"contains_answer": 1}', '{"contains_answer": true, "extra": 1}', 'broken'):
            with self.subTest(reply=reply), self.assertRaises(ValueError):
                self.select([chunk(1)], reply)

    def test_generation_error_keeps_failed_attempt_and_prior_decision(self):
        details = {}
        self.model.side_effect = [output(True), RuntimeError("api failed")]
        with self.assertRaisesRegex(RuntimeError, "api failed"):
            select_evidence("Q", [chunk(1), chunk(2)], budget=self.budget, selection_metadata=details)
        self.assertEqual(details["relevant_ids"], [1])
        self.assertEqual(details["status"], "error")
        self.assertEqual(details["attempts"][1]["error"]["type"], "RuntimeError")

    def test_budget_counts_question_and_gap_labels_not_just_fragments(self):
        self.model.return_value = "answer [1]"
        with self.assertRaises(InputBudgetExceeded):
            generate_answer("Q" * 90, [chunk(1, "short")], budget=self.budget)
        self.model.assert_not_called()

    def test_answer_receives_exact_measured_messages_without_second_truncation(self):
        chunks = [chunk(1, "joint one"), chunk(2, "joint two")]
        self.model.return_value = "Answer [1, 2]"
        result = generate_answer("Q", chunks, missing_parts=["Unknown"], budget_missing_parts=["Large"],
                                 budget=self.budget)
        messages = answer_messages("Q", chunks, ["Unknown"], ["Large"])
        self.assertEqual(self.counter.call_args.args[0], messages)
        self.assertEqual(self.model.call_args.args[0], messages)
        self.assertEqual(self.model.call_args.kwargs["max_tokens"], 30)
        self.assertIn("из-за бюджета", result["answer"])
        self.assertEqual(len(result["sources"]), 2)

    def test_preflight_blocks_selector_before_generation(self):
        self.counter.side_effect = None
        self.counter.return_value = 10000
        with self.assertRaises(InputBudgetExceeded):
            self.select([chunk(1)], output(True))
        self.model.assert_not_called()

    def test_counter_failure_never_falls_back_to_char_estimate(self):
        self.counter.side_effect = RuntimeError("count failed")
        with self.assertRaisesRegex(RuntimeError, "count failed"):
            self.select([chunk(1)], output(True))
        self.model.assert_not_called()

    def test_invalid_budget_fails_before_io(self):
        for values in ({"max_input_tokens": True}, {"max_output_tokens": -1}, {"context_tokens": 100}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                AnswerBudget(**values)



if __name__ == "__main__":
    unittest.main()
