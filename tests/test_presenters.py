from __future__ import annotations

from pathlib import Path

from hf_skills.app.presenters import compact_installed_rows, compact_update_rows, update_rows
from hf_skills.vendor.fast_agent_core.models import InstalledSkillSource, SkillProvenance, SkillUpdateInfo
from hf_skills.vendor.fast_agent_core.service import InstalledSkillRecord
from hf_skills.vendor.fast_agent_core.registry import SkillManifest


def test_compact_update_rows_shortens_hashes_and_drops_location() -> None:
    updates = [
        SkillUpdateInfo(
            index=1,
            name="alpha",
            skill_dir=Path("/tmp/project/.claude/skills/alpha"),
            status="updated",
            detail="updated",
            current_revision="1234567890abcdef1234567890abcdef12345678",
            available_revision="abcdef0123456789abcdef0123456789abcdef01",
        )
    ]

    rows = compact_update_rows(updates)

    assert rows == [
        {
            "index": "1",
            "name": "alpha",
            "agent": ".claude",
            "status": "updated",
            "current": "1234567",
            "available": "abcdef0",
            "detail": "updated",
        }
    ]


def test_compact_update_rows_shows_shared_agent_root() -> None:
    updates = [
        SkillUpdateInfo(
            index=1,
            name="alpha",
            skill_dir=Path("/tmp/project/.agents/skills/alpha"),
            status="updated",
            detail="updated",
            current_revision="1234567890abcdef1234567890abcdef12345678",
            available_revision="abcdef0123456789abcdef0123456789abcdef01",
        )
    ]

    rows = compact_update_rows(updates)

    assert rows[0]["agent"] == ".agents"


def test_compact_installed_rows_shows_agent_and_short_github_provenance(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".codex" / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    source = InstalledSkillSource(
        schema_version=1,
        installed_via="marketplace",
        source_origin="remote",
        repo_url="https://github.com/huggingface/skills",
        repo_ref="main",
        repo_path="skills/alpha",
        source_url=None,
        installed_commit="1234567890abcdef1234567890abcdef12345678",
        installed_path_oid="deadbeef",
        installed_revision="1234567890abcdef1234567890abcdef12345678",
        installed_at="2026-02-25T01:02:03Z",
        content_fingerprint="sha256:deadbeef",
    )
    (skill_dir / ".skill-source.json").write_text(
        "{\n"
        '  "content_fingerprint": "sha256:deadbeef",\n'
        '  "installed_at": "2026-02-25T01:02:03Z",\n'
        '  "installed_commit": "1234567890abcdef1234567890abcdef12345678",\n'
        '  "installed_path_oid": "deadbeef",\n'
        '  "installed_revision": "1234567890abcdef1234567890abcdef12345678",\n'
        '  "installed_via": "marketplace",\n'
        '  "repo_path": "skills/alpha",\n'
        '  "repo_ref": "main",\n'
        '  "repo_url": "https://github.com/huggingface/skills",\n'
        '  "schema_version": 1,\n'
        '  "source_origin": "remote",\n'
        '  "source_url": null\n'
        "}\n",
        encoding="utf-8",
    )
    record = InstalledSkillRecord(
        name="alpha",
        skill_dir=skill_dir,
        manifest=SkillManifest(
            name="alpha",
            description="Alpha",
            body="body",
            path=skill_dir / "SKILL.md",
        ),
        provenance=SkillProvenance(status="managed", summary="", source=source),
    )

    rows = compact_installed_rows([record])

    assert rows == [
        {
            "index": "1",
            "name": "alpha",
            "agent": ".codex",
            "provenance": "huggingface/skills",
            "installed": "2026-02-25 01:02:03 revision: 1234567",
        }
    ]


def test_compact_installed_rows_marks_symlink_aliases(tmp_path: Path) -> None:
    target_dir = tmp_path / ".agents" / "skills" / "alpha"
    target_dir.mkdir(parents=True)
    alias_dir = tmp_path / ".claude" / "skills" / "alpha"
    alias_dir.parent.mkdir(parents=True, exist_ok=True)
    alias_dir.symlink_to(target_dir, target_is_directory=True)

    record = InstalledSkillRecord(
        name="alpha",
        skill_dir=alias_dir,
        manifest=SkillManifest(
            name="alpha",
            description="Alpha",
            body="body",
            path=alias_dir / "SKILL.md",
        ),
        provenance=SkillProvenance(status="managed", summary="", source=None),
    )

    rows = compact_installed_rows([record])

    assert rows == [
        {
            "index": "1",
            "name": "alpha",
            "agent": ".claude",
            "provenance": "(symlink)",
            "installed": "",
        }
    ]


def test_update_rows_keeps_full_metadata_for_json(tmp_path) -> None:
    updates = [
        SkillUpdateInfo(
            index=1,
            name="alpha",
            skill_dir=tmp_path / "managed-skills" / "alpha",
            status="updated",
            detail="updated",
            current_revision="1234567890abcdef1234567890abcdef12345678",
            available_revision="abcdef0123456789abcdef0123456789abcdef01",
        )
    ]

    rows = update_rows(updates, cwd=tmp_path)

    assert rows == [
        {
            "index": "1",
            "name": "alpha",
            "status": "updated",
            "location": "managed-skills/alpha",
            "current": "1234567890abcdef1234567890abcdef12345678",
            "available": "abcdef0123456789abcdef0123456789abcdef01",
            "detail": "updated",
        }
    ]
