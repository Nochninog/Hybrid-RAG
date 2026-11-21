"""Загрузка и индексация оригиналов, создание и индексация Wiki."""

from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from typing import Annotated
from urllib.parse import quote

from fastapi import File, HTTPException, Path as PathParam, Query, UploadFile
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.api.common import BodyLimitMiddleware, create_app, operation
from backend.database.read_document import read_document
from backend.database.catalog import (
    list_documents, list_wiki_pages, read_document_details, read_wiki_details,
)
from backend.documents.errors import DocumentValidationError
from backend.documents.operations import upload_document
from backend.documents.policy import MAX_FILE_SIZE
from backend.documents.validation import validate_document
from backend.ingestion.index_document import index_document
from backend.wiki.indexing import index_wiki_page
from backend.wiki.operations import create_wiki_page
from backend.wiki.links import save_wiki_link
from backend.wiki.suggest_wiki_links import suggest_wiki_links
from backend.storage.download_file import download_file

app = create_app("knowledge-service")
app.add_middleware(BodyLimitMiddleware, max_bytes=MAX_FILE_SIZE + 64 * 1024)
PositiveID = Annotated[int, Field(strict=True, gt=0)]
ResourceID = Annotated[int, PathParam(gt=0)]


class WikiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_ids: list[PositiveID] = Field(min_length=1, max_length=100)
    topic: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


@app.get("/documents")
def documents(query: Annotated[str, Query(max_length=500)] = "",
              limit: Annotated[int, Query(ge=1, le=100)] = 30,
              offset: Annotated[int, Query(ge=0)] = 0):
    with operation("list_documents"):
        return list_documents(query, limit, offset)


@app.get("/documents/{document_id}")
def document_details(document_id: ResourceID):
    with operation("read_document"):
        document = read_document_details(document_id)
    if document is None:
        raise HTTPException(404, "Документ не найден")
    return document


@app.get("/documents/{document_id}/original")
def original(document_id: ResourceID):
    with operation("download_document"):
        document = read_document_details(document_id)
        if document is None:
            raise HTTPException(404, "Документ не найден")
        bucket, key = read_document(document_id)
        response = download_file(bucket, key)
        body = response["Body"]

    def chunks():
        try:
            while block := body.read(64 * 1024):
                yield block
        finally:
            body.close()

    return StreamingResponse(chunks(), media_type="application/octet-stream", background=BackgroundTask(body.close), headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(document["filename"], safe=""),
        "Content-Length": str(response["ContentLength"]),
    })


@app.get("/wiki-pages")
def wiki_pages(query: Annotated[str, Query(max_length=500)] = "",
               limit: Annotated[int, Query(ge=1, le=100)] = 30,
               offset: Annotated[int, Query(ge=0)] = 0):
    with operation("list_wiki_pages"):
        return list_wiki_pages(query, limit, offset)


@app.get("/wiki-pages/{page_id}")
def wiki_details(page_id: ResourceID):
    with operation("read_wiki"):
        page = read_wiki_details(page_id)
    if page is None:
        raise HTTPException(404, "Wiki-страница не найдена")
    return page


@app.post("/documents", status_code=201)
def upload(file: Annotated[UploadFile, File()]):
    """Принимает файл multipart/form-data и возвращает ID активного набора."""
    # Отбрасываем каталоги Windows и POSIX, сохраняя исходное имя для замены.
    filename = PureWindowsPath(file.filename or "").name
    if not filename or filename in {".", ".."} or ":" in filename or "\x00" in filename:
        file.file.close()
        raise HTTPException(422, "Укажите допустимое имя файла")
    try:
        with TemporaryDirectory(prefix="corpdb-upload-") as directory:
            path = Path(directory) / filename
            size = 0
            with path.open("wb") as target:
                while block := file.file.read(1024 * 1024):
                    size += len(block)
                    if size > MAX_FILE_SIZE:
                        raise HTTPException(413, "Превышен допустимый размер документа")
                    target.write(block)
            try:
                validate_document(path)
            except DocumentValidationError as exc:
                raise HTTPException(422, str(exc)) from exc
            with operation("upload"):
                document, _, document_id = upload_document(path)
        with operation("index_document", document_id=document_id, uploaded=True):
            run_id = index_document(document_id, extension=document.extension)
        return {"document_id": document_id, "filename": document.original_filename,
                "index_run_id": str(run_id), "status": "indexed"}
    finally:
        file.file.close()


@app.post("/documents/{document_id}/index")
def reindex_document(document_id: ResourceID):
    """Повторяет индексацию сохранённого оригинала, не загружая его заново."""
    with operation("index_document", document_id=document_id):
        _, storage_key = read_document(document_id)
        run_id = index_document(document_id, extension=Path(storage_key).suffix.lower())
    return {"document_id": document_id, "index_run_id": str(run_id), "status": "indexed"}


@app.post("/wiki-pages", status_code=201)
def create_wiki(request: WikiRequest):
    """Создаёт Wiki по явно выбранным источникам, затем индексирует её."""
    with operation("create_wiki"):
        page_id = create_wiki_page(request.document_ids, request.topic)
    with operation("index_wiki", wiki_page_id=page_id, saved=True):
        chunk_ids = index_wiki_page(page_id)
    return {"wiki_page_id": page_id, "chunk_count": len(chunk_ids), "status": "indexed"}


@app.post("/wiki-pages/{page_id}/index")
def reindex_wiki(page_id: ResourceID):
    with operation("index_wiki", wiki_page_id=page_id):
        chunk_ids = index_wiki_page(page_id)
    return {"wiki_page_id": page_id, "chunk_count": len(chunk_ids), "status": "indexed"}


@app.post("/wiki-pages/{page_id}/links")
def build_links(page_id: ResourceID):
    """Явно оценивает кандидатов и сохраняет положительные направленные связи."""
    with operation("suggest_wiki_links", wiki_page_id=page_id):
        result = suggest_wiki_links(page_id)
    saved = 0
    for link in result["links"]:
        with operation("save_wiki_links", wiki_page_id=page_id, saved_links=saved):
            save_wiki_link(**link)
        saved += 1
    return {"wiki_page_id": page_id, "saved_links": saved, "status": "completed"}
