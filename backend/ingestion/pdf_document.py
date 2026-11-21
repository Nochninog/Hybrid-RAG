"""Разбор текстового PDF по расположению и оформлению текста."""

import io
import re
from collections import Counter
from dataclasses import replace

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException

from backend.ingestion.errors import ExtractionError
from backend.ingestion.models import DocumentBlock, ParsedDocument


def parse_pdf(document_id: int, content_bytes: bytes) -> ParsedDocument:
    blocks = []
    try:
        with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
            sizes = Counter(
                round(char["size"], 1)
                for page in pdf.pages for char in page.chars
                if char["text"].strip()
            )
            body_size = sizes.most_common(1)[0][0] if sizes else 12
            heading_sizes = sorted(
                (size for size in sizes if size > body_size * 1.1), reverse=True
            )
            for page in pdf.pages:
                blocks.extend(_parse_page(page, body_size, heading_sizes))
    except PdfminerException as exc:
        raise ExtractionError(f"Не удалось разобрать PDF: {exc}") from exc
    return ParsedDocument(document_id, tuple(
        replace(block, position=index) for index, block in enumerate(blocks)
    ))


def _parse_page(page, body_size: float, heading_sizes: list[float]) -> list[DocumentBlock]:
    tables = page.find_tables()
    # Убираем символы таблиц из обычного текста, чтобы не дублировать их.
    text_page = page.filter(lambda obj: not (
        obj["object_type"] == "char" and any(
            left <= (obj["x0"] + obj["x1"]) / 2 <= right
            and top <= (obj["top"] + obj["bottom"]) / 2 <= bottom
            for left, top, right, bottom in (table.bbox for table in tables)
        )
    ))
    items = []
    for table in tables:
        text = "\n".join(
            "\t".join((cell or "").replace("\n", " ") for cell in row)
            for row in table.extract()
        )
        if text.strip():
            items.append((table.bbox, "table", text, None))

    for line in text_page.extract_text_lines():
        chars = [char for char in line["chars"] if char["text"].strip()]
        if not chars:
            continue
        text = line["text"]
        size = Counter(round(char["size"], 1) for char in chars).most_common(1)[0][0]
        level = None
        if all(re.search(r"Courier|Mono|Consolas", c["fontname"], re.I) for c in chars):
            kind = "code"
        elif size in heading_sizes:
            kind = "heading"
            level = min(heading_sizes.index(size) + 1, 6)
        elif (len(text) < 120 and not text.endswith((".", ",", ";"))
              and all("bold" in c["fontname"].lower() for c in chars)):
            kind = "heading"
            level = min(len(heading_sizes) + 1, 6)
        elif re.match(r"^(?:[-*•‣▪–]|\d+[.)]|[а-яa-z][.)])\s+", text, re.I):
            kind = "list"
        else:
            kind = "paragraph"
        bbox = (line["x0"], line["top"], line["x1"], line["bottom"])
        items.append((bbox, kind, text, level))

    blocks = []
    previous_bottom = 0
    for bbox, kind, text, level in sorted(items, key=lambda item: (item[0][1], item[0][0])):
        if (blocks and kind in {"paragraph", "list", "code"}
                and blocks[-1].kind == kind and bbox[1] - previous_bottom < body_size * 0.8):
            blocks[-1] = replace(blocks[-1], text=blocks[-1].text + "\n" + text)
        else:
            blocks.append(DocumentBlock(
                position=0, kind=kind, text=text, heading_level=level,
                page_start=page.page_number, page_end=page.page_number,
            ))
        previous_bottom = bbox[3]
    return blocks
