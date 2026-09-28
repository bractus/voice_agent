"""
Generate the small document fixtures used by the extraction, store, and API tests.

Run from the project root:
    .venv/bin/python tests/fixtures/generate_fixtures.py

Every text fixture holds well over 200 characters of extractable text (the
minimum a document needs to be considered readable). image_only.pdf draws an
image and has no text layer, so extraction must report it as unreadable.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent

PARAGRAPH_1 = (
    "Consistent hashing maps both servers and keys onto the same hash ring, so "
    "adding or removing a server only remaps the keys between it and its neighbour. "
    "Distributed caches use it to avoid a full reshuffle when the cluster changes size."
)
PARAGRAPH_2 = (
    "The Raft consensus algorithm elects a single leader that appends entries to a "
    "replicated log. A write is committed once a majority of followers acknowledge it, "
    "which keeps the cluster consistent even when a minority of nodes fail."
)

RESUME_TEXT = (
    "Jordan Example - Senior Backend Engineer\n\n"
    "Experience: Five years at Acme Payments building a Kafka-based ledger service in Go, "
    "and two years at Globex Logistics leading the migration of a monolith to Kubernetes.\n\n"
    "Skills: Go, Python, PostgreSQL, Kafka, Kubernetes, Terraform.\n\n"
    "Projects: Designed an idempotent payment-retry pipeline processing 2 million events a day."
)


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf(objects: list[bytes]) -> bytes:
    """Assemble a PDF from numbered object bodies, computing the xref table."""
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(out)


def _stream(content: bytes, extra: str = "") -> bytes:
    return f"<< /Length {len(content)}{extra} >>\nstream\n".encode() + content + b"\nendstream"


def make_text_pdf(paragraphs: list[str]) -> bytes:
    lines = []
    for paragraph in paragraphs:
        # Wrap roughly at 80 characters so each line stays on the page.
        words, line = paragraph.split(), ""
        for word in words:
            if len(line) + len(word) + 1 > 80:
                lines.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        lines.append(line)
        lines.append("")
    ops = ["BT", "/F1 11 Tf", "14 TL", "50 780 Td"]
    for line in lines:
        ops.append(f"({_escape_pdf_text(line)}) Tj T*")
    ops.append("ET")
    content = "\n".join(ops).encode("latin-1")
    return _build_pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        _stream(content),
    ])


def make_image_only_pdf() -> bytes:
    # An 8x8 greyscale gradient, drawn full-page. No text operators at all.
    pixels = bytes((x * 32 + y * 4) % 256 for y in range(8) for x in range(8))
    content = b"q 512 0 0 512 50 200 cm /Im1 Do Q"
    return _build_pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
        b"/Resources << /XObject << /Im1 4 0 R >> >> /Contents 5 0 R >>",
        _stream(pixels, " /Type /XObject /Subtype /Image /Width 8 /Height 8 "
                        "/ColorSpace /DeviceGray /BitsPerComponent 8"),
        _stream(content),
    ])


def make_docx(path: Path) -> None:
    from docx import Document

    doc = Document()
    for block in RESUME_TEXT.split("\n\n"):
        doc.add_paragraph(block)
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Certification"
    table.rows[0].cells[1].text = "Certified Kubernetes Administrator"
    doc.save(path)


def make_epub(path: Path) -> None:
    container = (
        '<?xml version="1.0"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles>\n'
        "</container>\n"
    )
    # The manifest lists chapter 2 first; the spine puts chapter 1 first.
    # Extraction must follow the spine.
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Distributed Systems Notes</dc:title><dc:identifier id=\"id\">fixture</dc:identifier>"
        "</metadata>\n"
        "  <manifest>\n"
        '    <item id="ch2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>\n'
        '    <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>\n'
        "  </manifest>\n"
        '  <spine><itemref idref="ch1"/><itemref idref="ch2"/></spine>\n'
        "</package>\n"
    )

    def chapter(title: str, body: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>'
            f"{title}</title><style>p {{ color: black; }}</style></head>"
            f"<body><h1>{title}</h1><p>{body}</p></body></html>\n"
        )

    with zipfile.ZipFile(path, "w") as zf:
        # The EPUB spec requires "mimetype" first and uncompressed.
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/chapter1.xhtml", chapter("Chapter One: Hashing", PARAGRAPH_1))
        zf.writestr("OEBPS/chapter2.xhtml", chapter("Chapter Two: Consensus", PARAGRAPH_2))


def main() -> None:
    (FIXTURES_DIR / "sample.pdf").write_bytes(make_text_pdf([PARAGRAPH_1, PARAGRAPH_2]))
    (FIXTURES_DIR / "resume.pdf").write_bytes(make_text_pdf(RESUME_TEXT.split("\n\n")))
    (FIXTURES_DIR / "image_only.pdf").write_bytes(make_image_only_pdf())
    (FIXTURES_DIR / "sample.txt").write_text(f"{PARAGRAPH_1}\n\n{PARAGRAPH_2}\n", encoding="utf-8")
    (FIXTURES_DIR / "sample.md").write_text(
        f"# Distributed Systems Notes\n\n## Hashing\n\n{PARAGRAPH_1}\n\n## Consensus\n\n{PARAGRAPH_2}\n",
        encoding="utf-8",
    )
    make_docx(FIXTURES_DIR / "sample.docx")
    make_epub(FIXTURES_DIR / "sample.epub")
    print(f"Fixtures written to {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
