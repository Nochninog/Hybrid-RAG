"""Контракты чтения для веб-интерфейса и закрытие потока оригинала."""

import io
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.knowledge import app


class CatalogAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_catalog_search_and_pagination_are_passed_to_storage(self):
        result = {"items": [{"id": 2, "filename": "Правила.md", "indexed": True}],
                  "total": 42, "limit": 20, "offset": 20}
        with patch("corpdb.api.knowledge.list_documents", return_value=result) as read:
            response = self.client.get("/documents", params={"query": "Правила", "limit": 20, "offset": 20})
        self.assertEqual(response.json(), result)
        read.assert_called_once_with("Правила", 20, 20)

    def test_invalid_pagination_never_reads_storage(self):
        with patch("corpdb.api.knowledge.list_documents") as read:
            for query in ["limit=0", "limit=101", "offset=-1"]:
                self.assertEqual(self.client.get("/documents?" + query).status_code, 422)
        read.assert_not_called()

    def test_missing_resources_return_404(self):
        with patch("corpdb.api.knowledge.read_document_details", return_value=None), \
             patch("corpdb.api.knowledge.read_wiki_details", return_value=None), \
             patch("corpdb.api.knowledge.download_file") as download:
            for path in ["/documents/9", "/documents/9/original", "/wiki-pages/9"]:
                self.assertEqual(self.client.get(path).status_code, 404)
        download.assert_not_called()

    def test_download_stream_is_closed_and_filename_encoded(self):
        body = io.BytesIO(b"original text")
        with patch("corpdb.api.knowledge.read_document_details", return_value={"filename": "Правила.md"}), \
             patch("corpdb.api.knowledge.read_document", return_value=("bucket", "key")), \
             patch("corpdb.api.knowledge.download_file", return_value={"Body": body, "ContentLength": 13}):
            response = self.client.get("/documents/9/original")
        self.assertEqual(response.content, b"original text")
        self.assertTrue(body.closed)
        self.assertIn("filename*=UTF-8''%D0", response.headers["content-disposition"])
        self.assertEqual(response.headers["content-type"], "application/octet-stream")

    def test_wiki_detail_preserves_markdown_and_source_ids(self):
        page = {"id": 3, "title": "Тема", "content": "# Правила\nТекст", "document_ids": [9]}
        with patch("corpdb.api.knowledge.read_wiki_details", return_value=page):
            self.assertEqual(self.client.get("/wiki-pages/3").json(), page)

    def test_document_details_do_not_require_object_storage(self):
        item = {"id": 3, "filename": "file.md", "indexed": True, "size_bytes": 42}
        with patch("corpdb.api.knowledge.read_document_details", return_value=item), \
             patch("corpdb.api.knowledge.download_file") as download:
            self.assertEqual(self.client.get("/documents/3").json(), item)
        download.assert_not_called()

    def test_wiki_catalog_returns_real_counts(self):
        result = {"items": [{"id": 2, "title": "Тема", "document_ids": [3], "link_count": 4}],
                  "total": 1, "limit": 30, "offset": 0}
        with patch("corpdb.api.knowledge.list_wiki_pages", return_value=result):
            self.assertEqual(self.client.get("/wiki-pages").json(), result)


if __name__ == "__main__":
    unittest.main()
