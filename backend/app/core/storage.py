"""Object storage client for rendered artifacts (P04).

WHY abstract this at all: same rationale as `EmbeddingClient` (P03) and the
LLM client (AGENTS.md §3) — one interface every caller (renderer, tests,
eventually assembly in P07/P08) depends on. Swapping providers, or running
fully offline in tests without a MinIO container, means picking a different
subclass in `get_storage_client()` — no other file changes.

WHY a `put`/`get` pair keyed by string, not a richer filesystem-like API:
callers only ever need "store these bytes under this name" and "fetch them
back" — anything more (listing, deleting, presigned URLs) can be added to
the interface when a real caller needs it, not speculatively now.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import get_settings


class StorageClient(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str) -> None:
        """Store `data` under `key`, overwriting any existing object."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Return the bytes stored under `key`."""


class S3StorageClient(StorageClient):
    """Real implementation, backed by `boto3`'s S3 client — works against
    both AWS S3 and any S3-compatible endpoint (MinIO, here)."""

    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, bucket: str) -> None:
        import boto3

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()


class InMemoryStorageClient(StorageClient):
    """Deterministic, offline stand-in — no network, no MinIO container.

    A plain dict on the instance is enough: `get_storage_client()` caches
    one instance per process (see below), so everything written during a
    test run or a dev session is readable back within that same process,
    which is all callers need.
    """

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._objects[key] = data

    def get(self, key: str) -> bytes:
        return self._objects[key]


@lru_cache
def get_storage_client() -> StorageClient:
    """Cached for the same reason `get_embedding_client` is: constructing a
    real provider client per call would be wasteful, and callers should not
    care which provider is configured. Note the in-memory dict lives on the
    cached instance too, so `storage_provider=memory` behaves like a single
    shared bucket for the life of the process."""
    settings = get_settings()
    if settings.storage_provider == "memory":
        return InMemoryStorageClient()
    if settings.storage_provider == "s3":
        return S3StorageClient(
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            bucket=settings.s3_bucket,
        )
    raise ValueError(f"Unknown storage_provider: {settings.storage_provider!r}")
