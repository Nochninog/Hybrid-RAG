"""Генерация текста через GigaChat 3 Ultra без дополнительного SDK."""

import os
import ssl
from uuid import uuid4

import httpx
from dotenv import load_dotenv


def generate_text(messages: list[dict[str, str]], *, response_schema: dict | None = None) -> str:
    """Получает токен по ключу авторизации и отправляет один запрос к модели."""
    load_dotenv()
    credentials = os.getenv("GIGACHAT_CREDENTIALS")
    if not credentials:
        raise ValueError("Добавьте GIGACHAT_CREDENTIALS в .env")

    payload = {"model": "GigaChat-3-Ultra", "messages": messages}
    if response_schema is not None:
        payload["response_format"] = {
            "type": "json_schema", "schema": response_schema, "strict": True,
        }
    context = ssl.create_default_context(cafile=os.getenv("GIGACHAT_CA_BUNDLE"))
    with httpx.Client(verify=context, timeout=60) as client:
        response = client.post(
            "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
            headers={"Authorization": f"Basic {credentials}", "RqUID": str(uuid4())},
            data={"scope": os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")},
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        response = client.post(
            "https://api.giga.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        response.raise_for_status()
        choice = response.json()["choices"][0]

    if choice["finish_reason"] != "stop":
        raise ValueError(f"Генерация не завершена: {choice['finish_reason']}")
    text = choice["message"]["content"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("GigaChat вернул пустой текст")
    return text
