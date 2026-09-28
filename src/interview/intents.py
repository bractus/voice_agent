"""
Deterministic matching of what the candidate says about the interview itself.

The interview type comes from the setup screen and GPT-Live judges readiness,
so only two things are matched here: an explicit request to end the interview
(specs/002-gpt-live-interview/research.md §6) and an explicit "I'm done" at the
end of an answer (§7). Plain phrase matching keeps it instant and testable.
Whole-phrase matching only.
"""
from __future__ import annotations

import re
import unicodedata

# Only explicit requests end the interview; a bare "stop" inside a technical
# answer ("the producer will stop") must not.
_STOP_PHRASES = (
    "stop the interview", "end the interview", "finish the interview",
    "stop this interview", "end this interview", "finish this interview",
    "let's stop here", "lets stop here", "let's end here", "lets end here",
    "let's stop now", "lets stop now", "let's end now", "lets end now",
    "let's wrap up", "lets wrap up",
    "that's enough for today", "thats enough for today",
    "i'm done with the interview", "im done with the interview",
    "we can stop here", "we can end here",
)

# Brazilian Portuguese (research.md §13). Matched without accents.
_STOP_PHRASES_PT_BR = (
    "vamos encerrar a entrevista", "encerrar a entrevista", "terminar a entrevista",
    "vamos terminar por aqui", "vamos parar por aqui", "pode encerrar a entrevista",
    "chega por hoje", "quero parar a entrevista", "finalizar a entrevista",
)

_PHRASES_BY_LANGUAGE = {"en": _STOP_PHRASES, "pt-BR": _STOP_PHRASES_PT_BR}

# "I've finished this answer" (research.md §7). Only matched at the very end of what the
# candidate has said, so "the build was done by Friday, and then..." doesn't count.
_DONE_PHRASES = (
    "that's it", "thats it", "that's all", "thats all", "that's my answer", "thats my answer",
    "i'm done", "im done", "i am done", "i'm finished", "im finished", "i am finished",
    "that's everything", "thats everything", "done", "finished",
)
_DONE_PHRASES_PT_BR = (
    "pronto", "terminei", "acabei", "finalizei", "e isso", "e isso ai", "so isso", "era isso",
    "essa e a minha resposta", "essa e minha resposta",
)

_DONE_BY_LANGUAGE = {"en": _DONE_PHRASES, "pt-BR": _DONE_PHRASES_PT_BR}


def _normalise(text: str) -> str:
    """Lowercase, drop accents, turn punctuation (except apostrophes) into spaces, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text.lower().replace("’", "'"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return " ".join(text.split())


def _contains(normalised: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9']){re.escape(term)}(?![a-z0-9'])", normalised) is not None


def _contains_any(normalised: str, terms: tuple[str, ...]) -> bool:
    return any(_contains(normalised, term) for term in terms)


def is_stop_request(text: str, language: str = "en") -> bool:
    """Return True only for an explicit request, in the interview's language, to end the interview."""
    phrases = tuple(_normalise(p) for p in _PHRASES_BY_LANGUAGE.get(language, _STOP_PHRASES))
    return _contains_any(_normalise(text), phrases)


def ends_with_done(text: str, language: str = "en") -> bool:
    """Return True when the candidate's last words say, explicitly, that the answer is finished."""
    words = _normalise(text).split()
    phrases = (_normalise(p).split() for p in _DONE_BY_LANGUAGE.get(language, _DONE_PHRASES))
    return any(words[-len(phrase):] == phrase for phrase in phrases)
