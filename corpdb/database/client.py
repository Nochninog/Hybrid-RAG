import os

import psycopg
from dotenv import load_dotenv
from contextlib import contextmanager

from corpdb.database.errors import (
    DatabaseError,
    DatabaseWriteError,
)

def create_connection():
    load_dotenv()

    return psycopg.connect(
    dbname=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host="127.0.0.1",
    port=5432,
    connect_timeout=5,
    )

@contextmanager
def transaction_connection():
    commit_started = False

    try:
        with create_connection() as connection:
            yield connection
            commit_started = True
    except psycopg.Error as exc:
        if commit_started:
            raise DatabaseError(
                "Не удалось подтвердить сохранение метаданных. "
                "Новый объект оставлен в MinIO до проверки."
            ) from exc

        raise DatabaseWriteError(
            "Не удалось записать метаданные в PostgreSQL."
        ) from exc
