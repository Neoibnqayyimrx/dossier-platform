"""Provider-abstracted LLM client (AGENTS.md §3), used only by the
narrative generation service (P05) to fill prose narrative slots.

WHY abstract this at all: fourth occurrence of the same shape as the
embedding client (P03) and storage client (P04) — one interface every
caller depends on, a config-selected implementation, a cached getter.
Swapping providers (or running fully offline in tests) means picking a
different subclass in `get_llm_client()` — no other file changes.

WHY `messages` is a list of {role, content} dicts rather than a single
prompt string: this is the shape every chat-style LLM API actually takes
(system instruction + a conversation), and keeping it generic here means a
future multi-turn use (e.g. "revise this narrative given reviewer
feedback") doesn't need a new interface method.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import get_settings


class LLMClient(ABC):
    @abstractmethod
    def generate(self, system: str, messages: list[dict[str, str]], max_tokens: int = 1024) -> str:
        """Return the model's text response to `messages`, following
        `system`'s instructions."""


class GeminiLLMClient(LLMClient):
    """Real implementation, backed by Google's `google-genai` SDK."""

    def __init__(self, api_key: str, model: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate(self, system: str, messages: list[dict[str, str]], max_tokens: int = 1024) -> str:
        from google.genai import types

        contents = [
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages
        ]
        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
            ),
        )
        return response.text


class FakeLLMClient(LLMClient):
    """Deterministic, offline stand-in — no network, no API key.

    WHY echo the last user message back, transformed, rather than return
    fixed boilerplate: the narrative service builds a prompt containing the
    structured facts and retrieved source excerpts as plain text. Reflecting
    that text back (prefixed, so it reads as generated prose rather than a
    literal echo) means tests exercising the full pipeline can assert the
    "generated" narrative actually contains the facts/sources it was given
    — a real hallucination-prone model could omit or distort them, but this
    stub can't accidentally hide a wiring bug behind canned text.
    """

    def generate(self, system: str, messages: list[dict[str, str]], max_tokens: int = 1024) -> str:
        last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        digest = hashlib.md5(last_user.encode()).hexdigest()[:8]
        return f"[fake-llm draft {digest}] {last_user}"


@lru_cache
def get_llm_client() -> LLMClient:
    """Cached for the same reason `get_embedding_client`/`get_storage_client`
    are: constructing a real provider client per call would be wasteful,
    and callers should not care which provider is configured."""
    settings = get_settings()
    if settings.llm_provider == "fake":
        return FakeLLMClient()
    if settings.llm_provider == "gemini":
        if not settings.llm_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=gemini requires LLM_API_KEY to be set. "
                "Set LLM_PROVIDER=fake for offline dev/test."
            )
        return GeminiLLMClient(api_key=settings.llm_api_key, model=settings.llm_model)
    raise ValueError(f"Unknown llm_provider: {settings.llm_provider!r}")
