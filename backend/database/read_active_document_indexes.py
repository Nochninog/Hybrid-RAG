"""Текущие оригиналы и успешно активированные наборы индексации."""

from backend.database.client import transaction_connection


def read_active_document_indexes() -> list[tuple[int, str, str]]:
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, storage_key, active_index_run_id FROM documents "
                "WHERE active_index_run_id IS NOT NULL ORDER BY id"
            )
            return [(document_id, key, str(run)) for document_id, key, run in cursor.fetchall()]
