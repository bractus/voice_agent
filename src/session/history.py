"""
In-memory conversation history manager.

Maintains OpenAI-format message list for the current session.
All data is cleared when the session ends — nothing is persisted to disk.
"""
from __future__ import annotations

SYSTEM_PROMPT = (
    "You are a concise voice assistant. "
    "Answer ONLY what the user explicitly asked. "
    "Do not add unsolicited information, follow-up questions, disclaimers, or commentary. "
    "Keep responses short and conversational — suitable for text-to-speech delivery."
)


class ConversationHistory:
    """Thread-safe in-memory conversation history for a single voice session."""

    def __init__(self, system_prompt: str = SYSTEM_PROMPT) -> None:
        self._messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

    # ── Mutators ──────────────────────────────────────────────────────────────

    def add_user_message(self, text: str) -> None:
        """Append a transcribed user utterance."""
        self._messages.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str) -> None:
        """Append a completed assistant response."""
        self._messages.append({"role": "assistant", "content": text})

    def discard_last_assistant(self) -> bool:
        """
        Remove the most recent assistant message when a barge-in occurs.

        Returns True if a message was discarded, False if history had no
        assistant message at the tail (no-op guard).
        """
        if self._messages and self._messages[-1]["role"] == "assistant":
            self._messages.pop()
            return True
        return False

    def clear(self) -> None:
        """Reset history, keeping only the system prompt."""
        system = self._messages[0]
        self._messages = [system]

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_messages(self) -> list[dict[str, str]]:
        """Return the full OpenAI-format message list (includes system prompt)."""
        return list(self._messages)

    def __len__(self) -> int:
        return len(self._messages)
