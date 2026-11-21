import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.embeddings.qwen import embed_texts


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("corpdb.embeddings.qwen.load_dotenv"))
        self.enterContext(patch.dict("os.environ", {"CLOUD_RU_API_KEY": "test-key"}))
        self.factory = self.enterContext(patch("corpdb.embeddings.qwen.OpenAI"))
        self.client = self.factory.return_value.__enter__.return_value

    def test_vectors_follow_input_order(self):
        self.client.embeddings.create.return_value.data = [
            SimpleNamespace(index=1, embedding=[0.3, 0.4]),
            SimpleNamespace(index=0, embedding=[0.1, 0.2]),
        ]
        self.assertEqual(embed_texts(["Первый", "Второй"]), [[0.1, 0.2], [0.3, 0.4]])
        self.client.embeddings.create.assert_called_once_with(
            model="Qwen/Qwen3-Embedding-0.6B", input=["Первый", "Второй"]
        )
        self.factory.assert_called_once_with(
            api_key="test-key", base_url="https://foundation-models.api.cloud.ru/v1"
        )
        self.factory.return_value.__exit__.assert_called_once()

    def test_empty_input_does_not_create_client(self):
        self.assertEqual(embed_texts([]), [])
        self.factory.assert_not_called()

    def test_incomplete_or_duplicate_indices_are_rejected(self):
        for indices in ([0], [0, 0], [0, 2]):
            with self.subTest(indices=indices):
                self.client.embeddings.create.return_value.data = [
                    SimpleNamespace(index=index, embedding=[0.1, 0.2]) for index in indices
                ]
                with self.assertRaises(ValueError):
                    embed_texts(["Первый", "Второй"])
