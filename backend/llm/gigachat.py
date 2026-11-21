"""Генерация текста через GigaChat 3 Ultra без дополнительного SDK."""

import json
import os
import ssl
from uuid import uuid4

import httpx
from dotenv import load_dotenv


class IncompleteGenerationError(ValueError):
    """API завершил генерацию с причиной, отличной от stop."""

    def __init__(self, finish_reason: str):
        self.finish_reason = finish_reason
        super().__init__(f"Генерация не завершена: {finish_reason}")


def generate_text(
    messages: list[dict[str, str]], *, response_schema: dict | None = None,
    response_metadata: dict | None = None,
    max_tokens: int | None = None,
) -> str:
    """Генерирует текст; max_tokens явно резервирует верхнюю границу ответа."""
    payload = _payload(messages, response_schema)
    if max_tokens is not None:
        if type(max_tokens) is not int or max_tokens <= 0:
            raise ValueError("max_tokens должен быть положительным целым числом")
        payload["max_tokens"] = max_tokens
    result = _post("chat/completions", payload)
    if response_metadata is not None:
        response_metadata.update({"usage": result.get("usage"), "model": result.get("model")})
    choice = result["choices"][0]
    if response_metadata is not None:
        response_metadata["finish_reason"] = choice.get("finish_reason")
    if choice["finish_reason"] != "stop":
        raise IncompleteGenerationError(choice["finish_reason"])
    text = choice["message"]["content"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("GigaChat вернул пустой текст")
    return text


def _payload(messages, response_schema=None):
    payload = {"model": "GigaChat-3-Ultra", "messages": messages}
    if response_schema is not None:
        payload["response_format"] = {
            "type": "json_schema", "schema": response_schema, "strict": True,
        }
    return payload


def count_message_tokens(messages: list[dict], *, response_schema: dict | None = None) -> int:
    """Оценка полного сериализованного входа, включая роли и JSON-схему.

    /tokens/count считает строки, а не внутренний chat template сервера.
    Вызывающий код обязан оставить запас на протокольные накладные расходы.
    Ошибку счётчика не заменяем приблизительным числом символов.
    """
    serialized = json.dumps(_payload(messages, response_schema), ensure_ascii=False)
    result = _post("tokens/count", {"model": "GigaChat-3-Ultra", "input": [serialized]})
    if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
        raise ValueError("Некорректный ответ подсчёта токенов GigaChat")
    tokens = result[0].get("tokens")
    if type(tokens) is not int or tokens < 0:
        raise ValueError("Некорректное число токенов GigaChat")
    return tokens


def _post(endpoint: str, payload: dict):
    """Один авторизованный запрос; секреты не возвращаются вызывающему коду."""
    load_dotenv()
    credentials = os.getenv("GIGACHAT_CREDENTIALS")
    if not credentials:
        raise ValueError("Добавьте GIGACHAT_CREDENTIALS в .env")

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
            "https://api.giga.chat/v1/" + endpoint,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        response.raise_for_status()
        return response.json()
