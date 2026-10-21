"""Подсчёт токенов текста для Qwen3-Embedding-0.6B."""

from functools import cache

from tokenizers import Tokenizer


@cache
def _get_tokenizer() -> Tokenizer:
    return Tokenizer.from_pretrained("Qwen/Qwen3-Embedding-0.6B")


def count_tokens(text: str) -> int:
    """Считает токены без добавления специальных; первый вызов скачивает токенизатор."""
    return len(_get_tokenizer().encode(text, add_special_tokens=False).ids)
