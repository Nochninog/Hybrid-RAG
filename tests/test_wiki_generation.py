"""Подготовка Wiki и вызов модели с подменой внешних сервисов."""

import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from backend.database.errors import DatabaseError
from backend.ingestion.errors import ExtractionError
from backend.llm.gigachat import generate_text
from backend.wiki.generation import get_document_texts, prepare_wiki_messages


class WikiInputTests(unittest.TestCase):
    def setUp(self):
        database = self.enterContext(patch("corpdb.database.read_document.transaction_connection"))
        self.cursor = database.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.download = self.enterContext(patch("corpdb.ingestion.extraction.download_file"))

    def test_full_texts_and_source_ids(self):
        self.cursor.fetchone.side_effect = [
            ("policy.MD",), ("bucket", "key-1"),
            ("instruction.txt",), ("bucket", "key-2"),
        ]
        first = io.BytesIO("# Отпуск\n\nПодать за 14 дней.".encode())
        second = io.BytesIO("Открыть кадровую систему.".encode())
        self.download.side_effect = [{"Body": first}, {"Body": second}]

        messages = prepare_wiki_messages([39, 40, 39], "Оформление отпуска")
        payload = json.loads(messages[1]["content"])
        self.assertEqual(payload["documents"], [
            {"document_id": 39, "filename": "policy.MD", "text": "# Отпуск\n\nПодать за 14 дней."},
            {"document_id": 40, "filename": "instruction.txt", "text": "Открыть кадровую систему."},
        ])
        self.assertEqual(payload["topic"], "Оформление отпуска")
        self.assertTrue(first.closed and second.closed)
        self.download.assert_any_call(bucket="bucket", storage_key="key-1")
        self.download.assert_any_call(bucket="bucket", storage_key="key-2")

    def test_invalid_selection_and_missing_document(self):
        with self.assertRaises(ValueError):
            get_document_texts([])
        with self.assertRaises(ValueError):
            prepare_wiki_messages([39], " ")
        self.cursor.fetchone.return_value = None
        with self.assertRaises(DatabaseError):
            get_document_texts([999])
        self.download.assert_not_called()

    def test_empty_and_unsupported_documents(self):
        self.cursor.fetchone.side_effect = [("empty.txt",), ("bucket", "key")]
        self.download.return_value = {"Body": io.BytesIO(b" \n")}
        with self.assertRaises(ExtractionError):
            get_document_texts([1])
        self.cursor.fetchone.side_effect = [("file.docx",)]
        with self.assertRaises(ExtractionError):
            get_document_texts([2])

    def test_pdf_uses_all_blocks_without_chunking(self):
        self.cursor.fetchone.side_effect = [("policy.pdf",), ("bucket", "key")]
        self.download.return_value = {"Body": io.BytesIO(b"pdf bytes")}
        blocks = (
            SimpleNamespace(kind="heading", heading_level=2, text="Отпуск"),
            SimpleNamespace(kind="paragraph", heading_level=None, text="Полный текст."),
        )
        with patch("corpdb.wiki.generation.parse_pdf", return_value=SimpleNamespace(blocks=blocks)) as parser:
            documents = get_document_texts([39])
        self.assertEqual(documents[0]["text"], "## Отпуск\n\nПолный текст.")
        parser.assert_called_once_with(39, b"pdf bytes")


class GigaChatTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("corpdb.llm.gigachat.load_dotenv"))
        self.enterContext(patch.dict("os.environ", {"GIGACHAT_CREDENTIALS": "test-key"}, clear=True))
        factory = self.enterContext(patch("corpdb.llm.gigachat.httpx.Client"))
        self.client = factory.return_value.__enter__.return_value

    def responses(self, finish_reason="stop", content="Wiki text"):
        token = MagicMock()
        token.json.return_value = {"access_token": "test-token"}
        result = MagicMock()
        result.json.return_value = {"choices": [{
            "finish_reason": finish_reason, "message": {"content": content},
        }]}
        self.client.post.side_effect = [token, result]
        return token, result

    def test_authorization_and_requested_model(self):
        self.responses()
        messages = [{"role": "user", "content": "test"}]
        self.assertEqual(generate_text(messages), "Wiki text")
        oauth, generation = self.client.post.call_args_list
        self.assertEqual(oauth.kwargs["headers"]["Authorization"], "Basic test-key")
        self.assertEqual(oauth.kwargs["data"], {"scope": "GIGACHAT_API_PERS"})
        self.assertEqual(generation.kwargs["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(generation.kwargs["json"], {"model": "GigaChat-3-Ultra", "messages": messages})

    def test_structured_response_format(self):
        self.responses(content='{"answer":true}')
        schema = {"type": "object", "properties": {"answer": {"type": "boolean"}},
                  "required": ["answer"], "additionalProperties": False}
        self.assertEqual(generate_text([], response_schema=schema), '{"answer":true}')
        payload = self.client.post.call_args.kwargs["json"]
        self.assertEqual(payload["response_format"], {
            "type": "json_schema", "schema": schema, "strict": True,
        })

    def test_incomplete_or_empty_response_is_rejected(self):
        for reason, content in [("length", "unfinished"), ("stop", " ")]:
            with self.subTest(reason=reason):
                self.responses(reason, content)
                with self.assertRaises(ValueError):
                    generate_text([{"role": "user", "content": "test"}])

    def test_oauth_error_stops_generation(self):
        token, _ = self.responses()
        token.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=httpx.Request("POST", "https://example.com"),
            response=httpx.Response(401),
        )
        with self.assertRaises(httpx.HTTPStatusError):
            generate_text([{"role": "user", "content": "test"}])
        self.assertEqual(self.client.post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
