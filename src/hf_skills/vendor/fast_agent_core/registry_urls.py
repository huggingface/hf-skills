from __future__ import annotations

from urllib.parse import urlparse


def format_marketplace_display_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc == "raw.githubusercontent.com":
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 4:
            org, repo = parts[:2]
            return f"https://github.com/{org}/{repo}"
    if parsed.netloc in {"github.com", "www.github.com"}:
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            org, repo = parts[:2]
            return f"https://github.com/{org}/{repo}"
    return url


def _canonical_registry_url(url: str) -> str:
    normalized = url.strip()
    parsed = urlparse(normalized)
    if parsed.netloc in {"github.com", "www.github.com"}:
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 5 and parts[2] == "blob":
            org, repo, _, ref = parts[:4]
            file_path = "/".join(parts[4:])
            return f"https://raw.githubusercontent.com/{org}/{repo}/{ref}/{file_path}"
    return normalized


def resolve_registry_urls(
    configured_urls: list[str] | None,
    *,
    default_urls: list[str],
    active_url: str | None = None,
) -> list[str]:
    registry_urls = list(configured_urls) if configured_urls else list(default_urls)
    if active_url:
        registry_urls.append(active_url)

    deduped: list[str] = []
    seen_source_urls: set[str] = set()
    for url in registry_urls:
        source_url = _canonical_registry_url(url)
        if source_url in seen_source_urls:
            continue
        seen_source_urls.add(source_url)
        deduped.append(url)
    return deduped
