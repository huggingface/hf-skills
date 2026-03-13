from __future__ import annotations

from pathlib import Path

from hf_skills.vendor.fast_agent_core import operations
from hf_skills.vendor.fast_agent_core.marketplace_parsing import parse_marketplace_payload
from hf_skills.vendor.fast_agent_core.models import MarketplaceSkill


def test_parse_marketplace_payload_normalizes_entries() -> None:
    payload = {
        "entries": [
            {
                "name": "alpha",
                "description": "Alpha skill",
                "repo_url": "https://github.com/example/skills",
                "repo_ref": "main",
                "repo_path": "skills/alpha",
            },
            {
                "name": "beta",
                "repo": "https://github.com/example/skills",
                "path": "skills/beta",
            },
        ]
    }

    skills = parse_marketplace_payload(payload, source_url="https://example.com/marketplace.json")

    assert len(skills) == 2
    assert skills[0].name == "alpha"
    assert skills[0].repo_path == "skills/alpha"
    assert skills[1].name == "beta"
    assert skills[1].repo_path == "skills/beta"


def test_parse_marketplace_payload_derives_fallback_name_from_repo_path_leaf() -> None:
    payload = {
        "entries": [
            {
                "repo_url": "https://github.com/example/skills",
                "repo_path": "skills/alpha",
            }
        ]
    }

    skills = parse_marketplace_payload(payload)

    assert len(skills) == 1
    assert skills[0].name == "alpha"


def test_parse_marketplace_payload_derives_fallback_name_from_skill_file_path() -> None:
    payload = {
        "entries": [
            {
                "repo_url": "https://github.com/example/skills",
                "repo_path": "skills/alpha/SKILL.md",
            }
        ]
    }

    skills = parse_marketplace_payload(payload)

    assert len(skills) == 1
    assert skills[0].name == "alpha"


def test_parse_marketplace_payload_expands_plugin_skills_for_local_marketplace(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    marketplace = repo / ".claude-plugin" / "marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text("{}", encoding="utf-8")

    payload = {
        "plugins": [
            {
                "name": "bundle",
                "description": "Bundle description",
                "source": "./",
                "skills": ["skills/alpha", "skills/beta"],
            }
        ]
    }

    skills = parse_marketplace_payload(payload, source_url=str(marketplace))

    assert [skill.name for skill in skills] == ["alpha", "beta"]
    assert all(skill.repo_url == str(repo) for skill in skills)
    assert [skill.repo_path for skill in skills] == ["skills/alpha", "skills/beta"]


def test_parse_marketplace_payload_expands_plugin_skill_file_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    marketplace = repo / ".claude-plugin" / "marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text("{}", encoding="utf-8")

    payload = {
        "plugins": [
            {
                "name": "bundle",
                "source": "./",
                "skills": ["skills/alpha/SKILL.md", "skills/beta/SKILL.md"],
            }
        ]
    }

    skills = parse_marketplace_payload(payload, source_url=str(marketplace))

    assert [skill.name for skill in skills] == ["alpha", "beta"]
    assert [skill.repo_path for skill in skills] == ["skills/alpha/SKILL.md", "skills/beta/SKILL.md"]


def test_parse_marketplace_payload_preserves_github_subtree_prefix_for_plugin_skills() -> None:
    payload = {
        "plugins": [
            {
                "name": "bundle",
                "source": "https://github.com/example/skills/tree/main/plugins/foo",
                "skills": ["alpha", "beta"],
            }
        ]
    }

    skills = parse_marketplace_payload(payload)

    assert [skill.name for skill in skills] == ["alpha", "beta"]
    assert all(skill.repo_url == "https://github.com/example/skills" for skill in skills)
    assert all(skill.repo_ref == "main" for skill in skills)
    assert [skill.repo_path for skill in skills] == ["plugins/foo/alpha", "plugins/foo/beta"]


def test_select_skill_by_name_or_index() -> None:
    entries = [
        MarketplaceSkill(
            name="alpha",
            description=None,
            repo_url="https://example.com/a.git",
            repo_ref=None,
            repo_path="skills/alpha",
        ),
        MarketplaceSkill(
            name="beta",
            description=None,
            repo_url="https://example.com/b.git",
            repo_ref=None,
            repo_path="skills/beta",
        ),
    ]

    assert operations.select_skill_by_name_or_index(entries, "1") == entries[0]
    assert operations.select_skill_by_name_or_index(entries, "beta") == entries[1]
    assert operations.select_skill_by_name_or_index(entries, "missing") is None
