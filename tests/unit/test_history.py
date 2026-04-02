"""
Unit tests for ConversationHistory.
"""
import pytest

from src.session.history import ConversationHistory, SYSTEM_PROMPT


class TestConversationHistory:
    def test_system_prompt_is_first_message(self):
        h = ConversationHistory()
        messages = h.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT

    def test_add_user_message(self):
        h = ConversationHistory()
        h.add_user_message("What is the capital of France?")
        messages = h.get_messages()
        assert len(messages) == 2
        assert messages[1] == {"role": "user", "content": "What is the capital of France?"}

    def test_add_assistant_message(self):
        h = ConversationHistory()
        h.add_user_message("Hello")
        h.add_assistant_message("Hi there!")
        messages = h.get_messages()
        assert len(messages) == 3
        assert messages[2] == {"role": "assistant", "content": "Hi there!"}

    def test_discard_last_assistant_removes_last_entry(self):
        h = ConversationHistory()
        h.add_user_message("Tell me about Paris")
        h.add_assistant_message("Paris is the capital of France.")
        discarded = h.discard_last_assistant()
        assert discarded is True
        messages = h.get_messages()
        assert len(messages) == 2
        assert messages[-1]["role"] == "user"

    def test_discard_last_assistant_no_op_when_last_is_user(self):
        h = ConversationHistory()
        h.add_user_message("Hello")
        discarded = h.discard_last_assistant()
        assert discarded is False
        assert len(h) == 2  # system + user

    def test_discard_last_assistant_no_op_on_empty_beyond_system(self):
        h = ConversationHistory()
        discarded = h.discard_last_assistant()
        assert discarded is False
        assert len(h) == 1  # only system prompt

    def test_clear_keeps_system_prompt(self):
        h = ConversationHistory()
        h.add_user_message("Hello")
        h.add_assistant_message("Hi")
        h.clear()
        messages = h.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "system"

    def test_get_messages_returns_copy(self):
        h = ConversationHistory()
        messages = h.get_messages()
        messages.append({"role": "user", "content": "injected"})
        assert len(h.get_messages()) == 1  # original unmodified

    def test_len(self):
        h = ConversationHistory()
        assert len(h) == 1
        h.add_user_message("A")
        assert len(h) == 2
        h.add_assistant_message("B")
        assert len(h) == 3

    def test_custom_system_prompt(self):
        custom = "You are a pirate."
        h = ConversationHistory(system_prompt=custom)
        assert h.get_messages()[0]["content"] == custom
