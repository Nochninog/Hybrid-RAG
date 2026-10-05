"""Проверки правил приёма документов и сохранности исходника."""

import tempfile
import unittest
from pathlib import Path

from corpdb.documents.errors import DocumentValidationError
from corpdb.documents.policy import MAX_FILE_SIZE
from corpdb.documents.validation import validate_document


class DocumentValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="corpdb-validation-")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def make_file(self, name: str, content: bytes = b"example") -> Path:
        path = self.root / name
        path.write_bytes(content)
        return path

    def test_metadata_and_original_are_preserved(self) -> None:
        path = self.make_file("report.md")
        document = validate_document(path)
        self.assertEqual(document.path, path.resolve())
        self.assertTrue(document.path.is_absolute())
        self.assertEqual(document.original_filename, "report.md")
        self.assertEqual(document.extension, ".md")
        self.assertEqual(document.size_bytes, 7)
        self.assertEqual(path.read_bytes(), b"example")

    def test_supported_extensions_are_case_insensitive(self) -> None:
        for extension in (".TXT", ".MD", ".PDF", ".DOCX"):
            with self.subTest(extension=extension):
                path = self.make_file("uppercase" + extension)
                self.assertEqual(validate_document(path).extension, extension.lower())

    def test_missing_file_is_rejected(self) -> None:
        with self.assertRaises(DocumentValidationError):
            validate_document(self.root / "missing.md")

    def test_directory_is_rejected(self) -> None:
        with self.assertRaises(DocumentValidationError):
            validate_document(self.root)

    def test_empty_file_is_rejected(self) -> None:
        with self.assertRaises(DocumentValidationError):
            validate_document(self.make_file("empty.txt", b""))

    def test_unsupported_extension_is_rejected(self) -> None:
        with self.assertRaises(DocumentValidationError):
            validate_document(self.make_file("report.exe"))

    def test_file_exactly_at_size_limit_is_accepted(self) -> None:
        path = self.root / "boundary.pdf"
        with path.open("wb") as stream:
            stream.truncate(MAX_FILE_SIZE)
        self.assertEqual(validate_document(path).size_bytes, MAX_FILE_SIZE)

    def test_file_above_size_limit_is_rejected(self) -> None:
        path = self.root / "oversized.pdf"
        with path.open("wb") as stream:
            stream.truncate(MAX_FILE_SIZE + 1)
        with self.assertRaises(DocumentValidationError):
            validate_document(path)


if __name__ == "__main__":
    unittest.main()
