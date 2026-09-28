"""
Contract tests for the documents HTTP API
(specs/001-mock-interview-agent/contracts/documents-api.md; unchanged by 002 apart from the embedding model).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.session_manager import session_manager
from src.documents.store import RESUME_MAX_BYTES
from src.interview.state import InterviewStage

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def client():
    from src.app import app
    return TestClient(app)


@pytest.fixture
def session():
    """A live session, as if its WebSocket were connected."""
    s = session_manager.create("docs-test")
    yield s
    session_manager.remove("docs-test")


def upload(client, kind: str, filename: str, data: bytes, session_id: str = "docs-test"):
    return client.post(
        f"/api/sessions/{session_id}/documents",
        data={"kind": kind},
        files={"file": (filename, data)},
    )


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# ── Resume ────────────────────────────────────────────────────────────────────

def test_resume_upload_returns_201(client, session):
    res = upload(client, "resume", "resume.pdf", fixture("resume.pdf"))
    assert res.status_code == 201
    body = res.json()
    assert body["kind"] == "resume"
    assert body["filename"] == "resume.pdf"
    assert body["format"] == "pdf"
    assert body["size_bytes"] == len(fixture("resume.pdf"))
    assert body["chunk_count"] == 0
    assert body["truncated"] is False
    assert body["document_id"]
    assert "Acme Payments" in session.documents.resume.text


@pytest.mark.parametrize("name", ["sample.docx", "sample.txt", "sample.md"])
def test_other_resume_formats_accepted(client, session, name):
    assert upload(client, "resume", name, fixture(name)).status_code == 201


def test_second_resume_replaces_first(client, session):
    upload(client, "resume", "first.txt", fixture("sample.txt"))
    upload(client, "resume", "second.md", fixture("sample.md"))
    listing = client.get("/api/sessions/docs-test/documents").json()
    assert listing["resume"]["filename"] == "second.md"


def test_epub_resume_is_unsupported(client, session):
    res = upload(client, "resume", "cv.epub", fixture("sample.epub"))
    assert res.status_code == 415
    assert res.json()["code"] == "UNSUPPORTED_FORMAT"
    assert res.json()["message"]


def test_oversized_resume_is_rejected(client, session):
    res = upload(client, "resume", "big.txt", b"a" * (RESUME_MAX_BYTES + 1))
    assert res.status_code == 413
    assert res.json()["code"] == "RESUME_TOO_LARGE"


def test_unreadable_resume_is_rejected_and_nothing_stored(client, session):
    res = upload(client, "resume", "scan.pdf", fixture("image_only.pdf"))
    assert res.status_code == 422
    assert res.json()["code"] == "DOCUMENT_UNREADABLE"
    assert session.documents.resume is None


def test_uploads_refused_after_interview_starts(client, session):
    session.interview.stage = InterviewStage.INTRODUCING
    res = upload(client, "resume", "resume.pdf", fixture("resume.pdf"))
    assert res.status_code == 409
    assert res.json()["code"] == "INTERVIEW_STARTED"


def test_unknown_session_is_404(client):
    res = upload(client, "resume", "resume.pdf", fixture("resume.pdf"), session_id="no-such-session")
    assert res.status_code == 404
    assert res.json()["code"] == "SESSION_NOT_FOUND"
    assert client.get("/api/sessions/no-such-session/documents").status_code == 404


def test_listing_shape_and_limits(client, session):
    upload(client, "resume", "resume.pdf", fixture("resume.pdf"))
    listing = client.get("/api/sessions/docs-test/documents").json()
    assert listing["resume"]["format"] == "pdf"
    assert listing["references"] == []
    assert listing["reference_bytes_total"] == 0
    assert listing["limits"] == {
        "reference_max_files": 5,
        "reference_max_bytes": 20 * 1024 * 1024,
        "resume_max_bytes": 5 * 1024 * 1024,
    }


# ── Reference material ────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["sample.pdf", "sample.txt", "sample.epub", "sample.md"])
def test_reference_formats_accepted(client, session, fake_embeddings, name):
    res = upload(client, "reference", name, fixture(name))
    assert res.status_code == 201
    body = res.json()
    assert body["kind"] == "reference"
    assert body["chunk_count"] >= 1
    assert body["truncated"] is False
    assert body["reference_count"] == 1
    assert body["reference_bytes_total"] == len(fixture(name))


def test_docx_reference_is_unsupported(client, session, fake_embeddings):
    res = upload(client, "reference", "notes.docx", fixture("sample.docx"))
    assert res.status_code == 415
    assert res.json()["code"] == "UNSUPPORTED_FORMAT"


def test_sixth_reference_file_rejected(client, session, fake_embeddings):
    for i in range(5):
        assert upload(client, "reference", f"notes{i}.md", fixture("sample.md")).status_code == 201
    res = upload(client, "reference", "sixth.md", fixture("sample.md"))
    assert res.status_code == 413
    assert res.json()["code"] == "REFERENCE_LIMIT_FILES"
    assert len(client.get("/api/sessions/docs-test/documents").json()["references"]) == 5


def test_reference_total_size_limit(client, session, fake_embeddings):
    md = fixture("sample.md")
    assert upload(client, "reference", "notes.md", md).status_code == 201
    too_big = b"a" * (20 * 1024 * 1024 - len(md) + 1)
    res = upload(client, "reference", "big.txt", too_big)
    assert res.status_code == 413
    assert res.json()["code"] == "REFERENCE_LIMIT_SIZE"
    listing = client.get("/api/sessions/docs-test/documents").json()
    assert [r["filename"] for r in listing["references"]] == ["notes.md"]


def test_embedding_unavailable_is_503(client, session, monkeypatch):
    from src.documents.errors import EmbeddingUnavailableError

    def down(texts):
        raise EmbeddingUnavailableError("The embedding model isn't available.")

    monkeypatch.setattr("src.documents.embeddings.embed_documents", down)
    res = upload(client, "reference", "notes.md", fixture("sample.md"))
    assert res.status_code == 503
    assert res.json()["code"] == "EMBEDDING_UNAVAILABLE"
    assert session.documents.references == []


# ── Resume suggestion (003) ───────────────────────────────────────────────────

def test_resume_upload_carries_the_suggestion(client, session, fake_resume_reader):
    fake_resume_reader["value"] = {"role": "Backend Engineer", "seniority": "senior"}
    body = upload(client, "resume", "resume.pdf", fixture("resume.pdf")).json()
    assert body["suggestion"] == {"role": "Backend Engineer", "seniority": "senior"}
    assert fake_resume_reader["calls"] == 1


def test_reader_failure_gives_null_suggestion(client, session, fake_resume_reader):
    fake_resume_reader["value"] = None
    res = upload(client, "resume", "resume.pdf", fixture("resume.pdf"))
    assert res.status_code == 201
    assert res.json()["suggestion"] is None


def test_reference_upload_has_no_suggestion(client, session, fake_embeddings, fake_resume_reader):
    body = upload(client, "reference", "sample.md", fixture("sample.md")).json()
    assert "suggestion" not in body
    assert fake_resume_reader["calls"] == 0
