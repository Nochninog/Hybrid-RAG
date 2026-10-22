from corpdb.database.client import transaction_connection


def insert_document(
    filename: str,
    storage_bucket: str,
    storage_key: str,
    size_bytes: int,
) -> tuple[int, str | None]:
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO documents (
                    filename,
                    storage_bucket,
                    storage_key,
                    size_bytes
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (storage_bucket, filename)
                DO NOTHING
                RETURNING id
                """,
                (filename, storage_bucket, storage_key, size_bytes),
            )
            created = cursor.fetchone()

            if created is not None:
                return created[0], None

            cursor.execute(
                """
                SELECT id, storage_key
                FROM documents
                WHERE storage_bucket = %s AND filename = %s
                FOR UPDATE
                """,
                (storage_bucket, filename),
            )
            document_id, old_storage_key = cursor.fetchone()

            cursor.execute(
                """
                UPDATE documents
                SET storage_key = %s, size_bytes = %s, active_index_run_id = NULL
                WHERE id = %s
                """,
                (storage_key, size_bytes, document_id),
            )

            return document_id, old_storage_key
