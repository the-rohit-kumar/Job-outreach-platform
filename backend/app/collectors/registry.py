"""Collector registry. Import a module here to make the source available."""
from __future__ import annotations

from .base import BaseCollector, CollectorContext, NormalizedLead, RobotsChecker, strip_html
from .github import GitHubCollector
from .hn import HNThreadsCollector
from .remotive import RemotiveCollector
from .remoteok import RemoteOKCollector
from .wwr import WWRCollector

# Step 2 core collectors.
CORE_COLLECTORS: list[type[BaseCollector]] = [
    HNThreadsCollector,
    RemoteOKCollector,
    WWRCollector,
    RemotiveCollector,
    GitHubCollector,
]

# Populated in step 8 with the remaining sources.
EXTRA_COLLECTORS: list[type[BaseCollector]] = []


def _build_registry() -> dict[str, BaseCollector]:
    registry: dict[str, BaseCollector] = {}
    for cls in list(CORE_COLLECTORS) + list(EXTRA_COLLECTORS):
        instance = cls()
        registry[instance.key] = instance
    return registry


REGISTRY: dict[str, BaseCollector] = _build_registry()


def get_collector(key: str) -> BaseCollector | None:
    return REGISTRY.get(key)


def all_collectors() -> list[BaseCollector]:
    return list(REGISTRY.values())


__all__ = [
    "BaseCollector",
    "CollectorContext",
    "NormalizedLead",
    "RobotsChecker",
    "REGISTRY",
    "get_collector",
    "all_collectors",
    "strip_html",
]
