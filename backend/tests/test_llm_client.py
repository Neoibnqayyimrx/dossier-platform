"""Tests for the provider-abstracted LLM client (P05): the offline fake
stub, and provider selection/error handling in get_llm_client()."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.llm.client import FakeLLMClient, GeminiLLMClient, get_llm_client


def test_fake_llm_client_reflects_the_prompt_content():
    client = FakeLLMClient()
    output = client.generate("system instructions", [{"role": "user", "content": "the facts"}])
    assert "the facts" in output


def test_fake_llm_client_is_deterministic():
    client = FakeLLMClient()
    messages = [{"role": "user", "content": "same input"}]
    assert client.generate("sys", messages) == client.generate("sys", messages)


def test_get_llm_client_fake_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    get_settings.cache_clear()
    get_llm_client.cache_clear()
    try:
        assert isinstance(get_llm_client(), FakeLLMClient)
    finally:
        get_settings.cache_clear()
        get_llm_client.cache_clear()


def test_get_llm_client_gemini_without_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    get_llm_client.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="LLM_API_KEY"):
            get_llm_client()
    finally:
        get_settings.cache_clear()
        get_llm_client.cache_clear()


def test_get_llm_client_gemini_with_key_builds_real_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")
    get_settings.cache_clear()
    get_llm_client.cache_clear()
    try:
        assert isinstance(get_llm_client(), GeminiLLMClient)
    finally:
        get_settings.cache_clear()
        get_llm_client.cache_clear()


def test_get_llm_client_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "not-a-real-provider")
    get_settings.cache_clear()
    get_llm_client.cache_clear()
    try:
        with pytest.raises(ValueError, match="Unknown llm_provider"):
            get_llm_client()
    finally:
        get_settings.cache_clear()
        get_llm_client.cache_clear()
