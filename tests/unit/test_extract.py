"""Unit tests for src/documents/extract.py."""
import io
import zipfile
from pathlib import Path

import pytest

from src.documents.errors import DocumentUnreadableError, UnsupportedFormatError
from src.documents.extract import detect_format, extract_text

FIXTURES = Path(__file__).parent.parent / "fixtures"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestDetectFormat:
    @pytest.mark.parametrize("filename, expected", [
        ("cv.pdf", "pdf"), ("CV.PDF", "pdf"), ("cv.docx", "docx"), ("book.epub", "epub"),
        ("notes.txt", "txt"), ("notes.md", "md"), ("notes.markdown", "md"),
    ])
    def test_known_extensions(self, filename, expected):
        assert detect_format(filename) == expected

    @pytest.mark.parametrize("filename", ["cv.rtf", "cv.doc", "noextension", ""])
    def test_unknown_extensions(self, filename):
        assert detect_format(filename) is None


class TestExtractText:
    def test_pdf(self):
        text = extract_text(fixture("sample.pdf"), "sample.pdf")
        assert "Consistent hashing" in text
        assert "Raft consensus" in text

    def test_docx_includes_paragraphs_and_tables(self):
        text = extract_text(fixture("sample.docx"), "sample.docx")
        assert "Acme Payments" in text
        assert "Certified Kubernetes Administrator" in text

    @pytest.mark.parametrize("name", ["sample.txt", "sample.md"])
    def test_plain_text_and_markdown(self, name):
        text = extract_text(fixture(name), name)
        assert "Consistent hashing" in text

    def test_latin1_text_falls_back_cleanly(self):
        data = ("Café résumé " * 30).encode("latin-1")
        assert "Café résumé" in extract_text(data, "notes.txt")

    def test_image_only_pdf_is_unreadable(self):
        with pytest.raises(DocumentUnreadableError):
            extract_text(fixture("image_only.pdf"), "scan.pdf")

    def test_too_little_text_is_unreadable(self):
        with pytest.raises(DocumentUnreadableError):
            extract_text(b"Just a few words.", "short.txt")

    def test_pdf_extension_on_non_pdf_bytes_is_unsupported(self):
        with pytest.raises(UnsupportedFormatError):
            extract_text(b"This is not a PDF at all. " * 20, "fake.pdf")

    def test_docx_extension_on_non_zip_bytes_is_unsupported(self):
        with pytest.raises(UnsupportedFormatError):
            extract_text(b"plain text pretending to be a docx " * 20, "fake.docx")

    def test_corrupt_zip_as_docx_is_unreadable(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("random.txt", "not a word document")
        with pytest.raises(DocumentUnreadableError):
            extract_text(buf.getvalue(), "broken.docx")

    def test_unknown_extension_is_unsupported(self):
        with pytest.raises(UnsupportedFormatError):
            extract_text(b"{\\rtf1 hello}", "cv.rtf")


class TestEpub:
    def test_follows_spine_order_and_strips_markup(self):
        text = extract_text(fixture("sample.epub"), "notes.epub")
        # The manifest lists chapter 2 first; the spine puts chapter 1 first.
        assert text.index("Consistent hashing") < text.index("Raft consensus")
        assert "Chapter One: Hashing" in text
        assert "<p>" not in text and "</h1>" not in text
        # Text inside <style> and <title> isn't content.
        assert "color: black" not in text

    def test_zip_without_container_is_unreadable(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
        with pytest.raises(DocumentUnreadableError):
            extract_text(buf.getvalue(), "broken.epub")
