import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.llm.gigachat import IncompleteGenerationError, count_message_tokens, generate_text
from backend.llm.usage import summarize_usage
from evaluation.report_gigachat_usage import build_report, render_report


class GigaChatUsageTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("corpdb.llm.gigachat.load_dotenv"))
        self.enterContext(patch.dict("os.environ", {"GIGACHAT_CREDENTIALS": "test"}))
        self.enterContext(patch("corpdb.llm.gigachat.ssl.create_default_context"))
        factory = self.enterContext(patch("corpdb.llm.gigachat.httpx.Client"))
        self.client = factory.return_value.__enter__.return_value

    def respond(self, reason="stop", usage=None):
        auth, response = MagicMock(), MagicMock()
        auth.json.return_value = {"access_token": "test"}
        response.json.return_value = {
            "model": "GigaChat-3-Ultra:version", "usage": usage,
            "choices": [{"finish_reason": reason, "message": {"content": "Ответ"}}],
        }
        self.client.post.side_effect = [auth, response]

    def test_success_preserves_api_usage_and_string_interface(self):
        usage = {"prompt_tokens": 10, "completion_tokens": 4,
                 "precached_prompt_tokens": 7, "total_tokens": 14}
        self.respond(usage=usage)
        metadata = {}
        self.assertEqual(generate_text([], response_metadata=metadata), "Ответ")
        self.assertEqual(metadata["usage"], usage)
        self.assertEqual(metadata["model"], "GigaChat-3-Ultra:version")
        self.assertEqual(metadata["finish_reason"], "stop")

    def test_blacklist_keeps_usage_before_raising(self):
        self.respond("blacklist", {"total_tokens": 12})
        metadata = {}
        with self.assertRaises(IncompleteGenerationError) as caught:
            generate_text([], response_metadata=metadata)
        self.assertEqual(caught.exception.finish_reason, "blacklist")
        self.assertEqual(metadata["usage"]["total_tokens"], 12)
        self.assertEqual(metadata["finish_reason"], "blacklist")

    def test_missing_usage_does_not_break_generation(self):
        self.respond()
        metadata = {}
        self.assertEqual(generate_text([], response_metadata=metadata), "Ответ")
        self.assertIsNone(metadata["usage"])

    def test_generation_enforces_output_token_reserve(self):
        self.respond()
        generate_text([{"role": "user", "content": "Q"}], max_tokens=4096)
        self.assertEqual(self.client.post.call_args.kwargs["json"]["max_tokens"], 4096)

    def test_count_serializes_full_messages_and_schema_for_same_model(self):
        auth, response = MagicMock(), MagicMock()
        auth.json.return_value = {"access_token": "test"}
        response.json.return_value = [{"tokens": 123}]
        self.client.post.side_effect = [auth, response]
        messages = [{"role": "system", "content": "System"}, {"role": "user", "content": "Вопрос"}]
        schema = {"type": "object"}
        self.assertEqual(count_message_tokens(messages, response_schema=schema), 123)
        request = self.client.post.call_args
        self.assertEqual(request.args[0], "https://api.giga.chat/v1/tokens/count")
        serialized = json.loads(request.kwargs["json"]["input"][0])
        self.assertEqual(serialized["messages"], messages)
        self.assertEqual(serialized["response_format"]["schema"], schema)
        self.assertEqual(serialized["model"], request.kwargs["json"]["model"])

    def test_invalid_counts_are_not_used_as_budget(self):
        for count in (True, -1, None, "12"):
            with self.subTest(count=count):
                auth, response = MagicMock(), MagicMock()
                auth.json.return_value = {"access_token": "test"}
                response.json.return_value = [{"tokens": count}]
                self.client.post.side_effect = [auth, response]
                with self.assertRaisesRegex(ValueError, "число токенов"):
                    count_message_tokens([])

    def test_missing_and_invalid_values_are_not_reported_as_zero(self):
        result = summarize_usage([
            {"usage": {"total_tokens": 0, "prompt_tokens": 4}},
            {}, {"usage": {"total_tokens": True, "prompt_tokens": -1}},
        ])
        self.assertEqual(result["tokens"]["total_tokens"], 0)
        self.assertEqual(result["calls_with_field"]["total_tokens"], 1)
        self.assertIsNone(result["tokens"]["completion_tokens"])
        self.assertFalse(result["complete"])

    def test_report_groups_errors_and_missing_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            path.write_text(json.dumps({"question_id": "q1", "mode": "wiki", "error": {}, "calls": [
                {"stage": "explore", "finish_reason": "blacklist", "usage": {"total_tokens": 9}},
                {"stage": "select_docs"},
            ]}), encoding="utf-8")
            report = build_report([path])
        self.assertEqual(report["all"]["tokens"]["total_tokens"], 9)
        self.assertEqual(report["groups"]["stage/wiki/explore"]["calls"], 1)
        self.assertIsNone(report["groups"]["stage/wiki/select_docs"]["tokens"]["total_tokens"])
        self.assertIn("9 (1/2)", render_report(report))
        self.assertIn("Н/д", render_report(report))


if __name__ == "__main__":
    unittest.main()
