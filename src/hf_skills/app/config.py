from __future__ import annotations

DEFAULT_REGISTRIES = [
    "https://github.com/huggingface/skills",
]

DEFAULT_REGISTRY = DEFAULT_REGISTRIES[0]


def resolve_registry(registry: str | None) -> str:
    return registry.strip() if registry and registry.strip() else DEFAULT_REGISTRY
