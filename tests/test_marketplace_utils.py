from __future__ import annotations

from pathlib import Path

import pytest

from hf_skills.vendor.fast_agent_core import formatting
from hf_skills.vendor.fast_agent_core.marketplace_source_utils import (
    candidate_marketplace_urls,
    derive_local_repo_root,
    parse_installed_source_fields,
)
from hf_skills.vendor.fast_agent_core.registry_urls import (
    format_marketplace_display_url,
    resolve_registry_urls,
)


def test_candidate_marketplace_urls_for_github_repo() -> None:
    assert candidate_marketplace_urls("https://github.com/example/skills") == [
        "https://raw.githubusercontent.com/example/skills/main/.claude-plugin/marketplace.json",
        "https://raw.githubusercontent.com/example/skills/main/marketplace.json",
        "https://raw.githubusercontent.com/example/skills/master/.claude-plugin/marketplace.json",
        "https://raw.githubusercontent.com/example/skills/master/marketplace.json",
    ]


def test_parse_installed_source_fields_validates_and_normalizes() -> None:
    payload = {
        "schema_version": 1,
        "installed_via": "marketplace",
        "source_origin": "remote",
        "repo_url": "  https://github.com/example/skills  ",
        "repo_ref": " main ",
        "repo_path": "skills/example",
        "source_url": "",
        "installed_commit": None,
        "installed_path_oid": None,
        "installed_revision": "abc123",
        "installed_at": "2026-02-25T00:00:00Z",
        "content_fingerprint": "sha256:deadbeef",
    }

    parsed = parse_installed_source_fields(
        payload,
        expected_schema_version=1,
        normalize_repo_path=lambda value: value.strip("/"),
    )

    assert parsed.repo_url == "https://github.com/example/skills"
    assert parsed.repo_ref == "main"
    assert parsed.source_url is None


def test_parse_installed_source_fields_rejects_invalid_repo_path() -> None:
    payload = {
        "schema_version": 1,
        "installed_via": "marketplace",
        "source_origin": "remote",
        "repo_url": "https://github.com/example/skills",
        "repo_ref": "main",
        "repo_path": "../escape",
        "source_url": None,
        "installed_commit": None,
        "installed_path_oid": None,
        "installed_revision": "abc123",
        "installed_at": "2026-02-25T00:00:00Z",
        "content_fingerprint": "sha256:deadbeef",
    }

    with pytest.raises(ValueError, match="repo_path is invalid"):
        parse_installed_source_fields(
            payload,
            expected_schema_version=1,
            normalize_repo_path=lambda _: None,
        )


def test_derive_local_repo_root_from_marketplace_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    marketplace = repo_root / ".claude-plugin" / "marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text("{}", encoding="utf-8")

    assert derive_local_repo_root(str(marketplace)) == str(repo_root)


def test_format_marketplace_display_url_for_github_variants() -> None:
    assert (
        format_marketplace_display_url("https://raw.githubusercontent.com/huggingface/skills/main/marketplace.json")
        == "https://github.com/huggingface/skills"
    )
    assert format_marketplace_display_url("https://github.com/huggingface/skills") == (
        "https://github.com/huggingface/skills"
    )


def test_resolve_registry_urls_dedupes_only_equivalent_sources() -> None:
    resolved = resolve_registry_urls(
        [
            "https://github.com/huggingface/skills/blob/main/marketplace.json",
            "https://raw.githubusercontent.com/huggingface/skills/main/marketplace.json",
            "https://github.com/anthropics/skills",
        ],
        default_urls=["https://github.com/huggingface/skills"],
    )

    assert resolved == [
        "https://github.com/huggingface/skills/blob/main/marketplace.json",
        "https://github.com/anthropics/skills",
    ]


def test_resolve_registry_urls_preserves_distinct_github_refs() -> None:
    resolved = resolve_registry_urls(
        [
            "https://raw.githubusercontent.com/huggingface/skills/main/marketplace.json",
            "https://raw.githubusercontent.com/huggingface/skills/dev/marketplace.json",
        ],
        default_urls=["https://github.com/huggingface/skills"],
    )

    assert resolved == [
        "https://raw.githubusercontent.com/huggingface/skills/main/marketplace.json",
        "https://raw.githubusercontent.com/huggingface/skills/dev/marketplace.json",
    ]


def test_format_revision_short_for_commit_hash() -> None:
    assert formatting.format_revision_short("0123456789abcdef") == "0123456"


def test_format_revision_short_for_named_revision() -> None:
    assert formatting.format_revision_short("main") == "main"


def test_format_installed_at_display_with_z_suffix() -> None:
    assert formatting.format_installed_at_display("2026-02-25T01:02:03Z") == "2026-02-25 01:02:03"
