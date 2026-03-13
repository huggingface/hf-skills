from __future__ import annotations

import subprocess
from pathlib import Path

from hf_skills.vendor.fast_agent_core import operations, service
from hf_skills.vendor.fast_agent_core.models import MarketplaceSkill
from hf_skills.vendor.fast_agent_core.provenance import read_installed_skill_source


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(repo: Path) -> None:
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True, text=True)
    _git(repo, "config", "user.email", "tests@example.com")
    _git(repo, "config", "user.name", "Test User")


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _write_skill(repo: Path, *, body: str, description: str = "Alpha skill") -> None:
    skill_dir = repo / "skills" / "alpha"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: alpha\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def _marketplace_skill(repo: Path) -> MarketplaceSkill:
    return MarketplaceSkill(
        name="alpha",
        description="Alpha skill",
        repo_url=str(repo),
        repo_ref=None,
        repo_path="skills/alpha",
        source_url=None,
    )


def test_install_writes_sidecar_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    commit = _commit_all(repo, "initial")

    destination_root = tmp_path / "managed-skills"
    install_dir = operations.install_marketplace_skill_sync(_marketplace_skill(repo), destination_root)

    assert (install_dir / "SKILL.md").exists()
    source, error = read_installed_skill_source(install_dir)
    assert error is None
    assert source is not None
    assert source.repo_url == str(repo)
    assert source.repo_path == "skills/alpha"
    assert source.installed_commit == commit


def test_update_check_and_apply(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")

    destination_root = tmp_path / "managed-skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), destination_root)

    _write_skill(repo, body="v2")
    updated_commit = _commit_all(repo, "update")

    updates = service.check_updates(destination_root)
    assert len(updates) == 1
    assert updates[0].status == "update_available"

    applied = service.apply_updates(destination_root, "alpha", force=False)
    assert len(applied) == 1
    assert applied[0].status == "updated"

    installed_skill = destination_root / "alpha" / "SKILL.md"
    assert "v2" in installed_skill.read_text(encoding="utf-8")
    source, error = read_installed_skill_source(destination_root / "alpha")
    assert error is None
    assert source is not None
    assert source.installed_commit == updated_commit


def test_update_skips_dirty_without_force_and_overwrites_with_force(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")

    destination_root = tmp_path / "managed-skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), destination_root)

    _write_skill(repo, body="v2")
    _commit_all(repo, "update")

    installed_skill = destination_root / "alpha" / "SKILL.md"
    installed_skill.write_text(installed_skill.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")

    updates = service.check_updates(destination_root)
    assert len(updates) == 1
    assert updates[0].status == "update_available"

    skipped = service.apply_updates(destination_root, "alpha", force=False)
    assert skipped[0].status == "skipped_dirty"
    assert "local edit" in installed_skill.read_text(encoding="utf-8")

    forced = service.apply_updates(destination_root, "alpha", force=True)
    assert forced[0].status == "updated"
    installed_text = installed_skill.read_text(encoding="utf-8")
    assert "v2" in installed_text
    assert "local edit" not in installed_text


def test_install_from_dirty_local_repo_records_unknown_revision(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")
    _write_skill(repo, body="dirty working tree")

    destination_root = tmp_path / "managed-skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), destination_root)

    source, error = read_installed_skill_source(destination_root / "alpha")
    assert error is None
    assert source is not None
    assert source.installed_commit is None
    assert source.installed_path_oid is None
    assert source.installed_revision == "local"

    updates = service.check_updates(destination_root)
    assert len(updates) == 1
    assert updates[0].status == "unknown_revision"


def test_install_skill_rolls_back_when_installed_skill_cannot_be_reloaded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    skill_dir = repo / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: alpha\n---\n\nbroken\n", encoding="utf-8")
    marketplace = repo / ".claude-plugin" / "marketplace.json"
    marketplace.parent.mkdir(parents=True, exist_ok=True)
    marketplace.write_text(
        '{"plugins":[{"name":"alpha","source":"./skills/alpha","skills":"./","description":"Broken skill"}]}',
        encoding="utf-8",
    )
    _commit_all(repo, "initial")

    destination_root = tmp_path / "managed-skills"

    try:
        service.install_skill_sync(str(marketplace), "alpha", destination_root=destination_root)
    except RuntimeError as exc:
        assert "Installed skill could not be reloaded" in str(exc)
    else:
        raise AssertionError("expected install to fail")

    assert not (destination_root / "alpha").exists()
