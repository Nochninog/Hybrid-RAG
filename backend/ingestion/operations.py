"""Обработка сохранённого документа до текстовых фрагментов."""

from backend.ingestion.chunking import chunk_document
from backend.ingestion.extraction import extraction_text, read_document_bytes
from backend.ingestion.markdown_document import parse_markdown
from backend.ingestion.pdf_document import parse_pdf
from backend.ingestion.models import DocumentBlock, DocumentChunk, ParsedDocument


def process_document(document_id: int, extension: str) -> tuple[DocumentChunk, ...]:
    if extension == ".pdf":
        document = parse_pdf(document_id, read_document_bytes(document_id))
    else:
        text = extraction_text(document_id, extension)
        if extension == ".md":
            document = parse_markdown(document_id, text)
        else:
            document = ParsedDocument(document_id, (DocumentBlock(0, "paragraph", text),))
    return chunk_document(document)
