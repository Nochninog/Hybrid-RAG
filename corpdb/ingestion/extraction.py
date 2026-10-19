from corpdb.database.read_document import read_document
from corpdb.storage.download_file import download_file
from corpdb.ingestion.errors import ExtractionError

from botocore.exceptions import BotoCoreError
from pypdf import PdfReader
from pypdf.errors import PyPdfError
import io

def extraction_text(document_id, extension):
    if extension not in {".txt", ".md", ".pdf"}:
        raise ExtractionError(f"Извлечение текста из {extension} пока не поддерживается.")

    storage_bucket, storage_key = read_document(document_id=document_id)

    response = download_file(bucket=storage_bucket, storage_key=storage_key)

    body = response['Body']
    try:
        try:
            content_bytes = body.read()
        finally:
            body.close()
        if extension == ".pdf":
            pdf_file = io.BytesIO(content_bytes)
            reader = PdfReader(pdf_file)

            content_text = ""
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    content_text += text + "\n"
        else:
            content_text = content_bytes.decode('utf-8')
    except (UnicodeDecodeError, PyPdfError, BotoCoreError) as exc:
        raise ExtractionError(f"Не удалось извлечь текст: {exc}") from exc

    return content_text