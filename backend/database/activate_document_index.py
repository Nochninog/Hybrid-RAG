"""Назначение готового набора фрагментов актуальному оригиналу."""

from contextlib import contextmanager
from uuid import UUID

from backend.database.client import transaction_connection
from backend.database.errors import DatabaseWriteError


@contextmanager
def locked_document_index(document_id: int):
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT storage_key, active_index_run_id FROM documents
                WHERE id = %s FOR UPDATE
                """,
                (document_id,),
            )
            yield cursor.fetchone()


def activate_document_index(
    document_id: int,
    storage_bucket: str,
    storage_key: str,
    index_run_id: UUID,
) -> UUID | None:
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT active_index_run_id FROM documents
                WHERE id = %s AND storage_bucket = %s AND storage_key = %s
                FOR UPDATE
                """,
                (document_id, storage_bucket, storage_key),
            )
            previous = cursor.fetchone()
            if previous is None:
                raise DatabaseWriteError(
                    "Документ удалён или заменён во время индексации; "
                    "новый набор фрагментов не назначен активным."
                )
            cursor.execute(
                """
                UPDATE documents
                SET active_index_run_id = %s
                WHERE id = %s AND storage_bucket = %s AND storage_key = %s
                RETURNING id
                """,
                (index_run_id, document_id, storage_bucket, storage_key),
            )
            return previous[0]
