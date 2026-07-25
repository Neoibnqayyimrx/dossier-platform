"""Provider-abstracted embedding client for the knowledge base (P03).

WHY abstract this at all: `EmbeddingClient` is the one interface every
caller (ingestion, retrieval, tests) depends on. Swapping providers, or
running fully offline in tests, means picking a different subclass in
`get_embedding_client()` — no other file changes. Same rationale AGENTS.md
§3 gives for the LLM client.

WHY `input_type` is a parameter, not baked into the interface: Voyage (and
most embedding APIs) train separate representations for "this text is a
document to be indexed" vs "this text is a search query" — passing the
right one measurably improves retrieval. Ingestion always embeds as
"document"; retrieval always embeds the query as "query". Getting this
backwards doesn't error, it just quietly retrieves worse results — the kind
of bug you can only catch by knowing the API contract, not from a type
checker.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import get_settings
from app.models.kb import EMBEDDING_DIMENSION

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class EmbeddingClient(ABC):
    @abstractmethod
    def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        """Return one vector of length EMBEDDING_DIMENSION per input text,
        in the same order."""


class VoyageEmbeddingClient(EmbeddingClient):
    """Real implementation, backed by the `voyageai` SDK."""

    def __init__(self, api_key: str, model: str) -> None:
        import voyageai

        self._client = voyageai.Client(api_key=api_key)
        self._model = model

    def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        result = self._client.embed(texts, model=self._model, input_type=input_type)
        return result.embeddings


class FakeEmbeddingClient(EmbeddingClient):
    """Deterministic, offline stand-in — no network, no API key.

    WHY hashed bag-of-words rather than random noise: a purely random
    vector per text would make every similarity search meaningless (nothing
    is ever "closer" to a query than anything else, so ingest->search
    round-trip tests couldn't tell success from failure). Hashing each
    token into one of EMBEDDING_DIMENSION buckets and counting gives crude
    but real lexical similarity — two chunks that share words end up with
    genuinely closer cosine distance — which is exactly what the ingest/
    retrieval tests need to exercise, without calling a real model.
    """

    def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSION
        for token in _TOKEN_RE.findall(text.lower()):
            bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % EMBEDDING_DIMENSION
            vector[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    """Cached for the same reason `get_settings` is: constructing a real
    provider client per call would be wasteful, and callers should not care
    which provider is configured."""
    settings = get_settings()
    if settings.embedding_provider == "fake":
        return FakeEmbeddingClient()
    if settings.embedding_provider == "voyage":
        if not settings.embedding_api_key:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=voyage requires EMBEDDING_API_KEY to be set. "
                "Set EMBEDDING_PROVIDER=fake for offline dev/test."
            )
        return VoyageEmbeddingClient(
            api_key=settings.embedding_api_key, model=settings.embedding_model
        )
    raise ValueError(f"Unknown embedding_provider: {settings.embedding_provider!r}")
