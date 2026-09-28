"""
Resume reader — suggests the role and seniority from an uploaded resume
(specs/003-role-seniority-setup/contracts/agents.md#resume-reader-new-small).

A small model call with a strict schema and an 8 s cap. It never raises and never
blocks the upload: anything unclear, slow or broken comes back as None.
"""
from __future__ import annotations

import asyncio
import json
import logging

from src import config
from src.interview.state import ROLE_MAX_CHARS, SENIORITIES, normalise_role
from src.openai_client import describe_error, get_async_client

logger = logging.getLogger(__name__)

READER_TIMEOUT_SECONDS = 8.0

READER_INSTRUCTIONS = """\
You read a candidate's resume and suggest the job they are most likely interviewing for.

1. Find the latest (or current) position.
2. role: that position's job title as written, WITHOUT the level word (e.g. "Senior Backend Engineer" \
→ "Backend Engineer"; "Desenvolvedora Pleno" → "Desenvolvedora"). At most 80 characters.
3. seniority: "junior", "mid" or "senior".
   - An explicit level word in the latest title wins: Intern, Trainee, Junior, Júnior, Estagiário, I → junior; \
Mid, Pleno, II → mid; Senior, Sênior, Staff, Principal, Lead, III → senior.
   - Otherwise use total professional experience: about 0–2 years junior, 2–5 mid, 5+ senior.
4. Use null for any value you are not reasonably sure of. Never guess."""

SUGGESTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["role", "seniority"],
    "properties": {
        "role": {"type": ["string", "null"]},
        "seniority": {"type": ["string", "null"], "enum": ["junior", "mid", "senior", None]},
    },
}


def parse_suggestion(raw: str | None) -> dict | None:
    """The model's JSON as {role, seniority}; None when unusable or when both are unknown."""
    try:
        data = json.loads(raw or "")
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    role = normalise_role(data.get("role"))
    if role is not None:
        role = role[:ROLE_MAX_CHARS].rstrip()
    seniority = data.get("seniority") if data.get("seniority") in SENIORITIES else None
    if role is None and seniority is None:
        return None
    return {"role": role, "seniority": seniority}


async def _call_model(text: str) -> str:
    response = await get_async_client().responses.create(
        model=config.OPENAI_QUESTION_MODEL,
        instructions=READER_INSTRUCTIONS,
        input=text[: config.RESUME_PROMPT_MAX_CHARS],
        reasoning={"effort": "low"},
        # Reasoning tokens count toward this limit too; 512 cut replies off in testing.
        max_output_tokens=2048,
        text={"format": {"type": "json_schema", "name": "resume_suggestion", "schema": SUGGESTION_SCHEMA, "strict": True}},
    )
    if response.status != "completed":
        return ""  # an incomplete reply parses to no suggestion
    return response.output_text


async def suggest_from_resume(text: str) -> dict | None:
    """Suggested role and seniority for this resume, or None. Never raises."""
    if not text or not text.strip():
        return None
    try:
        raw = await asyncio.wait_for(_call_model(text), timeout=READER_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.info("Resume reader timed out after %.0f s", READER_TIMEOUT_SECONDS)
        return None
    except Exception as exc:
        logger.warning("Resume reader failed: %s", describe_error(exc))
        return None
    return parse_suggestion(raw)
