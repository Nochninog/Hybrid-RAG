"""Сохранение готового текста или создание новой Wiki по выбранным документам."""

from backend.database.insert_wiki_page import insert_wiki_page
from backend.llm.gigachat import generate_text
from backend.wiki.generation import prepare_wiki_messages


def save_wiki_page(title: str, content: str, document_ids: list[int]) -> int:
    """Сохраняет Markdown и связи с источниками, возвращает ID новой страницы."""
    if not title.strip():
        raise ValueError("Укажите заголовок Wiki-страницы")
    if not content.strip():
        raise ValueError("Нельзя сохранить пустую Wiki-страницу")
    if not document_ids:
        raise ValueError("Укажите источники Wiki-страницы")
    return insert_wiki_page(title.strip(), content, list(dict.fromkeys(document_ids)))


def create_wiki_page(document_ids: list[int], topic: str) -> int:
    """Читает источники, генерирует текст и сохраняет новую страницу в PostgreSQL."""
    document_ids = list(dict.fromkeys(document_ids))
    messages = prepare_wiki_messages(document_ids, topic)
    content = generate_text(messages)
    return save_wiki_page(topic, content, document_ids)
