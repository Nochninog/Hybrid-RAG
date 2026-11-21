"""Очистка после подтверждённой активации без удаления параллельных наборов."""

import logging
from uuid import UUID

from weaviate.exceptions import WeaviateBaseError

from backend.database.activate_document_index import locked_document_index
from backend.database.errors import DatabaseError
from backend.indexes.delete_old_chunks import delete_old_chunks

logger = logging.getLogger(__name__)


def cleanup_document_index(
    document_id: int, active_run_id: UUID, previous_run_id: UUID | None
) -> None:
    try:
        with locked_document_index(document_id) as document:
            if document is not None and document[1] == active_run_id:
                delete_old_chunks(document_id, document[0], active_run_id, previous_run_id)
    except (DatabaseError, WeaviateBaseError, OSError):
        logger.warning(
            "Набор %s активирован, но очистка документа %s не завершена",
            active_run_id, document_id, exc_info=True,
        )
