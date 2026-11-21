"""HTTP-контракты двух сервисов без хранилищ и вызовов моделей."""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from backend.api.knowledge import app as knowledge_app
from backend.api.search import app as search_app
from backend.documents.policy import MAX_FILE_SIZE


class KnowledgeAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(knowledge_app)
        self.upload = self.enterContext(patch("corpdb.api.knowledge.upload_document"))
        self.index = self.enterContext(patch("corpdb.api.knowledge.index_document"))
        self.index.return_value = UUID(int=1)

    def test_upload_preserves_filename_and_cleans_temporary_file(self):
        paths = []

        def upload(path):
            paths.append(path)
            self.assertEqual(path.name, "report.MD")
            self.assertEqual(path.read_bytes(), b"# report")
            return SimpleNamespace(original_filename=path.name, extension=".md"), {}, 42

        self.upload.side_effect = upload
        response = self.client.post("/documents", files={"file": (r"C:\docs\report.MD", b"# report")})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["document_id"], 42)
        self.index.assert_called_once_with(42, extension=".md")
        self.assertFalse(paths[0].exists())

    def test_invalid_files_do_not_reach_storage(self):
        for filename, content in [("empty.md", b""), ("bad.exe", b"bad"), ("..", b"bad")]:
            with self.subTest(filename=filename):
                response = self.client.post("/documents", files={"file": (filename, content)})
                self.assertEqual(response.status_code, 422)
        self.upload.assert_not_called()

    def test_file_size_limit(self):
        response = self.client.post("/documents", files={"file": ("large.md", b"x" * (MAX_FILE_SIZE + 1))})
        self.assertEqual(response.status_code, 413)
        self.upload.assert_not_called()

    def test_request_size_limit_without_content_length(self):
        def body():
            yield b"--boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.md\"\r\n\r\n"
            for _ in range(22):
                yield b"x" * (1024 * 1024)
            yield b"\r\n--boundary--\r\n"

        response = self.client.post("/documents", content=body(),
                                    headers={"Content-Type": "multipart/form-data; boundary=boundary"})
        self.assertEqual(response.status_code, 413)
        self.upload.assert_not_called()

    def test_index_failure_returns_saved_id_and_cleans_file(self):
        paths = []

        def upload(path):
            paths.append(path)
            return SimpleNamespace(original_filename=path.name, extension=".md"), {}, 42

        self.upload.side_effect = upload
        self.index.side_effect = RuntimeError("secret-provider-response")
        response = self.client.post("/documents", files={"file": ("report.md", b"text")})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["document_id"], 42)
        self.assertEqual(response.json()["detail"]["stage"], "index_document")
        self.assertNotIn("secret-provider-response", response.text)
        self.assertFalse(paths[0].exists())

    def test_reindex_uses_saved_extension(self):
        with patch("corpdb.api.knowledge.read_document", return_value=("bucket", "key.PDF")):
            response = self.client.post("/documents/42/index")
        self.assertEqual(response.status_code, 200)
        self.index.assert_called_once_with(42, extension=".pdf")
        self.upload.assert_not_called()

    def test_wiki_creation_and_index(self):
        with patch("corpdb.api.knowledge.create_wiki_page", return_value=7) as create, \
             patch("corpdb.api.knowledge.index_wiki_page", return_value=(UUID(int=1),)) as index:
            response = self.client.post("/wiki-pages", json={"document_ids": [42], "topic": " Wiki "})
        self.assertEqual(response.status_code, 201)
        create.assert_called_once_with([42], "Wiki")
        index.assert_called_once_with(7)

    def test_wiki_index_failure_can_be_retried_without_generation(self):
        with patch("corpdb.api.knowledge.create_wiki_page", return_value=7) as create, \
             patch("corpdb.api.knowledge.index_wiki_page", side_effect=RuntimeError()):
            response = self.client.post("/wiki-pages", json={"document_ids": [42], "topic": "Wiki"})
        self.assertEqual(response.json()["detail"]["wiki_page_id"], 7)
        with patch("corpdb.api.knowledge.index_wiki_page", return_value=()) as index:
            retry = self.client.post("/wiki-pages/7/index")
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(create.call_count, 1)
        index.assert_called_once_with(7)

    def test_wiki_request_validation(self):
        with patch("corpdb.api.knowledge.create_wiki_page") as create:
            for payload in [{"document_ids": [], "topic": "Wiki"},
                            {"document_ids": [True], "topic": "Wiki"},
                            {"document_ids": [1], "topic": "  "}]:
                self.assertEqual(self.client.post("/wiki-pages", json=payload).status_code, 422)
        create.assert_not_called()

    def test_partial_link_save_reports_progress(self):
        links = [{"source_page_id": 7, "target_page_id": target, "explanation": "reason"}
                 for target in [8, 9]]
        with patch("corpdb.api.knowledge.suggest_wiki_links", return_value={"links": links}), \
             patch("corpdb.api.knowledge.save_wiki_link", side_effect=[None, RuntimeError()]):
            response = self.client.post("/wiki-pages/7/links")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["saved_links"], 1)


class SearchAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(search_app)

    def test_calls_full_workflow_and_keeps_sources_and_interruption(self):
        result = {"answer": "Ответ [1]", "sources": [{"document_id": 42}],
                  "missing_parts": [], "budget_missing_parts": [],
                  "explore_status": "interrupted", "explore_error": {"finish_reason": "blacklist"},
                  "selection_details": {"private_prompts": "text"}}
        with patch("corpdb.api.search.answer_question", return_value=result) as answer:
            response = self.client.post("/questions", json={"question": " Вопрос "})
        self.assertEqual(response.status_code, 200)
        answer.assert_called_once_with(question="Вопрос", limit=10, max_depth=2, max_expansions=20)
        self.assertEqual(response.json()["sources"], result["sources"])
        self.assertEqual(response.json()["explore_status"], "interrupted")
        self.assertNotIn("selection_details", response.json())

    def test_invalid_question_never_calls_workflow(self):
        with patch("corpdb.api.search.answer_question") as answer:
            for payload in [{"question": " "}, {"question": "q", "limit": 0},
                            {"question": "q", "max_depth": -1}, {"question": "q", "limit": True},
                            {"question": "q", "unknown": 1}]:
                self.assertEqual(self.client.post("/questions", json=payload).status_code, 422)
        answer.assert_not_called()

    def test_workflow_error_does_not_leak_provider_response(self):
        with patch("corpdb.api.search.answer_question", side_effect=RuntimeError("secret")):
            response = self.client.post("/questions", json={"question": "q"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret", response.text)

    def test_health_and_openapi(self):
        for app, service in [(knowledge_app, "knowledge-service"), (search_app, "search-service")]:
            client = TestClient(app)
            self.assertEqual(client.get("/health").json(), {"status": "ok", "service": service})
            self.assertEqual(client.get("/openapi.json").status_code, 200)


if __name__ == "__main__":
    unittest.main()
