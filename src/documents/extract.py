"""
Text extraction for uploaded documents.

Formats (research.md §3):
  - PDF      pypdf
  - DOCX     python-docx (paragraphs + table cells)
  - EPUB     standard library: zipfile + xml.etree (spine order) + html.parser
  - TXT / MD UTF-8, falling back to latin-1; Markdown is kept as plain text

The format comes from the file extension and is then checked against the
content, so a renamed file is reported as unsupported rather than
producing garbage.
"""
from __future__ import annotations

import io
import logging
import posixpath
import zipfile
from html.parser import HTMLParser
from pathlib import PurePath
from urllib.parse import unquote
from xml.etree import ElementTree

from src.config import MIN_EXTRACTED_CHARS
from src.documents.errors import DocumentUnreadableError, UnsupportedFormatError

logger = logging.getLogger(__name__)

_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".epub": "epub",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
}


def detect_format(filename: str) -> str | None:
    """Return the document format for `filename`'s extension, or None if unsupported."""
    return _EXTENSIONS.get(PurePath(filename).suffix.lower())


def extract_text(file_bytes: bytes, filename: str) -> str:
    """
    Extract plain text from an uploaded document.

    Raises:
        UnsupportedFormatError:  unknown extension, or content that doesn't match it.
        DocumentUnreadableError: corrupt file, or less than MIN_EXTRACTED_CHARS of text
                                 (e.g. an image-only PDF).
    """
    fmt = detect_format(filename)
    if fmt is None:
        raise UnsupportedFormatError(f"{filename} is not a supported file type.")

    _check_content_matches(fmt, file_bytes, filename)

    try:
        if fmt == "pdf":
            text = _extract_pdf(file_bytes)
        elif fmt == "docx":
            text = _extract_docx(file_bytes)
        elif fmt == "epub":
            text = _extract_epub(file_bytes)
        else:
            text = _decode_text(file_bytes)
    except (UnsupportedFormatError, DocumentUnreadableError):
        raise
    except Exception as exc:
        logger.warning("Could not extract text from %s: %s", filename, exc)
        raise DocumentUnreadableError(f"{filename} could not be read. It may be corrupt.") from exc

    text = _tidy(text)
    if len(text) < MIN_EXTRACTED_CHARS:
        raise DocumentUnreadableError(
            f"{filename} has no readable text. If it's a scanned document, "
            "try a version with selectable text."
        )
    return text


def _check_content_matches(fmt: str, data: bytes, filename: str) -> None:
    if fmt == "pdf" and not data.lstrip()[:5].startswith(b"%PDF"):
        raise UnsupportedFormatError(f"{filename} doesn't look like a PDF file.")
    if fmt in ("docx", "epub") and not zipfile.is_zipfile(io.BytesIO(data)):
        raise UnsupportedFormatError(f"{filename} doesn't look like a {fmt.upper()} file.")


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _extract_epub(data: bytes) -> str:
    """Read the chapters listed in the OPF spine, in order, as plain text."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        container = ElementTree.fromstring(zf.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile").get("full-path")
        opf = ElementTree.fromstring(zf.read(rootfile))
        base = posixpath.dirname(rootfile)

        manifest = {
            item.get("id"): item.get("href")
            for item in opf.findall(".//{*}manifest/{*}item")
        }
        parts = []
        for itemref in opf.findall(".//{*}spine/{*}itemref"):
            href = manifest.get(itemref.get("idref"))
            if not href:
                continue
            path = posixpath.normpath(posixpath.join(base, unquote(href)))
            parts.append(_html_to_text(zf.read(path).decode("utf-8", errors="replace")))
    return "\n\n".join(parts)


class _TextCollector(HTMLParser):
    """Collect visible text from (X)HTML, with line breaks at block elements."""

    _SKIP = {"head", "script", "style", "title"}
    _BLOCKS = {"p", "div", "br", "li", "tr", "section", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def _html_to_text(html: str) -> str:
    collector = _TextCollector()
    collector.feed(html)
    return "".join(collector.parts)


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _tidy(text: str) -> str:
    """Normalise line endings and drop runs of blank lines."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    tidy: list[str] = []
    for line in lines:
        if line or (tidy and tidy[-1]):
            tidy.append(line)
    return "\n".join(tidy).strip()
