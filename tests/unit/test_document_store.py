"""Unit tests for src/documents/store.py (resume handling and upload validation)."""
import pytest

from src.documents.errors import InterviewStartedError, LimitExceededError, UnsupportedFormatError
from src.documents.store import RESUME_MAX_BYTES, Document, DocumentSet


def resume(name: str = "cv.pdf", size: int = 1000, text: str = "resume text") -> Document:
    return Document(kind="resume", filename=name, format=name.rsplit(".", 1)[1], size_bytes=size, text=text)


class TestValidateResumeUpload:
    @pytest.mark.parametrize("name", ["cv.pdf", "cv.docx", "cv.txt", "cv.md"])
    def test_allowed_formats(self, name):
        assert DocumentSet().validate_upload("resume", name, 1000, uploads_allowed=True)

    def test_epub_is_not_a_resume_format(self):
        with pytest.raises(UnsupportedFormatError):
            DocumentSet().validate_upload("resume", "cv.epub", 1000, uploads_allowed=True)

    def test_exactly_at_the_limit_is_accepted(self):
        DocumentSet().validate_upload("resume", "cv.pdf", RESUME_MAX_BYTES, uploads_allowed=True)

    def test_over_the_limit_is_rejected(self):
        with pytest.raises(LimitExceededError) as exc:
            DocumentSet().validate_upload("resume", "cv.pdf", RESUME_MAX_BYTES + 1, uploads_allowed=True)
        assert exc.value.code == "RESUME_TOO_LARGE"
        assert exc.value.status == 413

    def test_uploads_refused_once_interview_started(self):
        with pytest.raises(InterviewStartedError) as exc:
            DocumentSet().validate_upload("resume", "cv.pdf", 1000, uploads_allowed=False)
        assert exc.value.status == 409

    def test_stage_is_checked_before_format(self):
        with pytest.raises(InterviewStartedError):
            DocumentSet().validate_upload("resume", "cv.rtf", 1000, uploads_allowed=False)


class TestSetResume:
    def test_second_resume_replaces_the_first(self):
        docs = DocumentSet()
        docs.set_resume(resume("old.pdf"))
        docs.set_resume(resume("new.md"))
        assert docs.resume.filename == "new.md"

    def test_oversized_resume_rejected(self):
        with pytest.raises(LimitExceededError):
            DocumentSet().set_resume(resume(size=RESUME_MAX_BYTES + 1))

    def test_resume_does_not_touch_reference_totals(self):
        docs = DocumentSet()
        docs.set_resume(resume(size=4000))
        assert docs.references == [] and docs.reference_bytes_total == 0


# ── Reference material ────────────────────────────────────────────────────────

import zlib  # noqa: E402

from src.documents.index import VectorIndex  # noqa: E402
from src.documents.store import REFERENCE_MAX_BYTES, REFERENCE_MAX_FILES  # noqa: E402


def _embed(text: str) -> list[float]:
    vec = [0.01] * 16
    for word in text.split():
        vec[zlib.crc32(word.encode()) % 16] += 1.0
    return vec


def make_index() -> VectorIndex:
    return VectorIndex(embed_documents=lambda ts: [_embed(t) for t in ts], embed_query=_embed)


def reference(name: str = "notes.md", size: int = 1000) -> Document:
    return Document(kind="reference", filename=name, format=name.rsplit(".", 1)[1], size_bytes=size, text="x")


def add(docs: DocumentSet, name: str = "notes.md", size: int = 1000, chunks=("chunk one", "chunk two")):
    doc = reference(name, size)
    docs.add_reference(doc, list(chunks), index_factory=make_index)
    return doc


class TestValidateReferenceUpload:
    @pytest.mark.parametrize("name", ["book.pdf", "notes.txt", "book.epub", "notes.md"])
    def test_allowed_formats(self, name):
        DocumentSet().validate_upload("reference", name, 1000, uploads_allowed=True)

    def test_docx_is_not_a_reference_format(self):
        with pytest.raises(UnsupportedFormatError):
            DocumentSet().validate_upload("reference", "notes.docx", 1000, uploads_allowed=True)

    def test_sixth_file_is_rejected(self):
        docs = DocumentSet()
        for i in range(REFERENCE_MAX_FILES):
            add(docs, f"notes{i}.md")
        with pytest.raises(LimitExceededError) as exc:
            docs.validate_upload("reference", "sixth.md", 10, uploads_allowed=True)
        assert exc.value.code == "REFERENCE_LIMIT_FILES"

    def test_total_size_limit(self):
        docs = DocumentSet()
        add(docs, "big.pdf", size=REFERENCE_MAX_BYTES - 100)
        docs.validate_upload("reference", "fits.md", 100, uploads_allowed=True)
        with pytest.raises(LimitExceededError) as exc:
            docs.validate_upload("reference", "too-much.md", 101, uploads_allowed=True)
        assert exc.value.code == "REFERENCE_LIMIT_SIZE"


class TestAddReference:
    def test_chunks_are_indexed_with_sequential_ids(self):
        docs = DocumentSet()
        first = add(docs, "a.md", chunks=("alpha one", "alpha two"))
        second = add(docs, "b.md", chunks=("beta one",))
        assert [c.chunk_id for c in docs.chunks] == [0, 1, 2]
        assert docs.chunks[2].document_id == second.document_id
        assert first.chunk_count == 2 and second.chunk_count == 1
        assert len(docs.index) == 3
        assert docs.reference_bytes_total == 2000

    def test_rejection_keeps_previously_accepted_files(self):
        docs = DocumentSet()
        add(docs, "kept.md", size=REFERENCE_MAX_BYTES)
        with pytest.raises(LimitExceededError):
            add(docs, "rejected.md", size=1)
        assert [d.filename for d in docs.references] == ["kept.md"]
        assert docs.reference_bytes_total == REFERENCE_MAX_BYTES

    def test_session_chunk_cap_truncates(self, monkeypatch):
        monkeypatch.setattr("src.documents.store.REFERENCE_MAX_CHUNKS", 3)
        docs = DocumentSet()
        first = add(docs, "a.md", chunks=("one", "two"))
        second = add(docs, "b.md", chunks=("three", "four", "five"))
        assert not first.truncated
        assert second.truncated and second.chunk_count == 1
        assert len(docs.chunks) == 3 and len(docs.index) == 3

    def test_embedding_failure_stores_nothing(self):
        def broken_index():
            return VectorIndex(embed_documents=lambda ts: (_ for _ in ()).throw(RuntimeError("down")),
                               embed_query=_embed)

        docs = DocumentSet()
        with pytest.raises(RuntimeError):
            docs.add_reference(reference(), ["some text"], index_factory=broken_index)
        assert docs.references == [] and docs.chunks == [] and docs.reference_bytes_total == 0
