import io
import unittest

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.ingestion.errors import ExtractionError
from backend.ingestion.pdf_document import parse_pdf


def make_pdf(*page_commands):
    writer = PdfWriter()
    for commands in page_commands:
        page = writer.add_blank_page(width=600, height=800)
        fonts = DictionaryObject()
        for name, face in (("F1", "Helvetica"), ("F2", "Helvetica-Bold"), ("F3", "Courier")):
            fonts[NameObject("/" + name)] = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/" + face),
            })
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): fonts})
        stream = DecodedStreamObject()
        stream.set_data(commands.encode("ascii"))
        page.replace_contents(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class PdfTests(unittest.TestCase):
    def test_structure_order_and_no_duplicate_table_text(self):
        document = parse_pdf(7, make_pdf(r"""
BT /F2 18 Tf 50 750 Td (Title) Tj ET
BT /F1 12 Tf 50 720 Td (A sufficiently long paragraph with ordinary text.) Tj ET
BT /F1 12 Tf 50 706 Td (The next line belongs to the same paragraph.) Tj ET
BT /F2 14 Tf 50 670 Td (Section) Tj ET
BT /F1 12 Tf 50 640 Td (1. First item) Tj ET
BT /F1 12 Tf 50 626 Td (2. Second item) Tj ET
BT /F3 12 Tf 50 590 Td (x = 1) Tj ET
BT /F3 12 Tf 50 576 Td (print\(x\)) Tj ET
50 500 m 250 500 l S 50 480 m 250 480 l S 50 460 m 250 460 l S
50 460 m 50 500 l S 150 460 m 150 500 l S 250 460 m 250 500 l S
BT /F1 12 Tf 55 485 Td (Name) Tj ET
BT /F1 12 Tf 155 485 Td (Value) Tj ET
BT /F1 12 Tf 55 465 Td (Alice) Tj ET
BT /F1 12 Tf 155 465 Td (42) Tj ET
BT /F1 12 Tf 50 420 Td (Text after the table.) Tj ET
"""))
        blocks = document.blocks
        self.assertEqual([b.kind for b in blocks], [
            "heading", "paragraph", "heading", "list", "code", "table", "paragraph"
        ])
        self.assertEqual([blocks[0].heading_level, blocks[2].heading_level], [1, 2])
        self.assertIn("\nThe next line", blocks[1].text)
        self.assertEqual(blocks[5].text, "Name\tValue\nAlice\t42")
        self.assertEqual("\n".join(b.text for b in blocks).count("Alice"), 1)
        self.assertEqual([b.position for b in blocks], list(range(len(blocks))))
        self.assertTrue(all(b.page_start == b.page_end == 1 for b in blocks))
        self.assertEqual(document.document_id, 7)

    def test_empty_pages_keep_source_numbers(self):
        document = parse_pdf(7, make_pdf("", "BT /F1 12 Tf 50 700 Td (Text.) Tj ET"))
        self.assertEqual(len(document.blocks), 1)
        self.assertEqual(document.blocks[0].kind, "paragraph")
        self.assertEqual(document.blocks[0].page_start, 2)
        self.assertEqual(parse_pdf(7, make_pdf("")).blocks, ())

    def test_invalid_pdf_has_application_error(self):
        with self.assertRaises(ExtractionError):
            parse_pdf(7, b"invalid PDF")
