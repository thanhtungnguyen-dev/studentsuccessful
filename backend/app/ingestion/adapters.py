"""The deliberately small boundary between external fetchers and persistence."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from backend.app.ingestion.dto import ExternalJobDTO


class UnsupportedSourceAdapterError(ValueError):
    """Raised when a caller names an adapter that was not explicitly registered."""


@runtime_checkable
class SourceAdapter(Protocol):
    """A fetcher that produces strict external-job facts.

    Adapters do network or vendor work here, before the service opens a database
    transaction.  They never receive a session or unit of work.
    """

    key: str
    source_authority: str

    def fetch(self) -> Iterable[ExternalJobDTO]: ...


class SourceAdapterRegistry:
    """Explicit allow-list of supported source adapters."""

    def __init__(self, adapters: Iterable[SourceAdapter] = ()):
        self._adapters: dict[str, SourceAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: SourceAdapter) -> None:
        key = getattr(adapter, "key", "")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,49}", key):
            raise ValueError("Source adapter key must be a safe 1-50 character identifier")
        normalized = key
        if normalized in self._adapters:
            raise ValueError(f"Source adapter already registered: {normalized}")
        self._adapters[normalized] = adapter

    def resolve(self, key: str) -> SourceAdapter:
        adapter = self._adapters.get(key)
        if adapter is None:
            raise UnsupportedSourceAdapterError(f"Unsupported source adapter: {key}")
        return adapter

    def supports(self, key: str) -> bool:
        return key in self._adapters

    def source_authority(self, key: str) -> str:
        """Return generic adapter metadata; legacy adapters stay structured."""

        return getattr(self.resolve(key), "source_authority", "TRUSTED_STRUCTURED")
