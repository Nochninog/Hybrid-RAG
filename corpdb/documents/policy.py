"""Правила приёма документов, общие для разных способов загрузки."""

ALLOWED_EXTENSIONS = frozenset({".txt", ".md", ".pdf", ".docx"})
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MiB
