import pytest

from src.config import OPENAI_API_KEY, OPENROUTER_API_KEY

# Integration tests call the real OpenAI and OpenRouter APIs and cost a little; they skip without a key.
requires_openai = pytest.mark.skipif(not OPENAI_API_KEY, reason="OPENAI_API_KEY not set")
requires_openrouter = pytest.mark.skipif(not OPENROUTER_API_KEY, reason="OPENROUTER_API_KEY not set")
