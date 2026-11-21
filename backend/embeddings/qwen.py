"""Векторизация текстов через Qwen в Cloud.ru."""

import os

from dotenv import load_dotenv
from openai import OpenAI


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Возвращает по одному вектору на текст в исходном порядке."""
    if not texts:
        return []

    load_dotenv()
    with OpenAI(
        api_key=os.getenv("CLOUD_RU_API_KEY"),
        base_url="https://foundation-models.api.cloud.ru/v1",
    ) as client:
        response = client.embeddings.create(
            model="Qwen/Qwen3-Embedding-0.6B",
            input=texts,
        )

    data = sorted(response.data, key=lambda item: item.index)
    if [item.index for item in data] != list(range(len(texts))):
        raise ValueError("Ответ Qwen не содержит по одному вектору на каждый текст")
    return [item.embedding for item in data]
