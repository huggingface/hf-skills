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


def _marketplace_skill_with_ref(repo: Path, repo_ref: str) -> MarketplaceSkill:
    return MarketplaceSkill(
        name="alpha",
        description="Alpha skill",
        repo_url=str(repo),
        repo_ref=repo_ref,
        repo_path="skills/alpha",
        source_url=None,
    )


def _marketplace_file(repo: Path, *, payload: str) -> Path:
    marketplace = repo / ".claude-plugin" / "marketplace.json"
    marketplace.parent.mkdir(parents=True, exist_ok=True)
    marketplace.write_text(payload, encoding="utf-8")
    return marketplace


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


def test_install_with_force_overwrites_existing_skill(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")

    destination_root = tmp_path / "managed-skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), destination_root)

    installed_skill = destination_root / "alpha" / "SKILL.md"
    installed_skill.write_text(installed_skill.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")

    _write_skill(repo, body="v2")
    updated_commit = _commit_all(repo, "update")

    operations.install_marketplace_skill_sync(_marketplace_skill(repo), destination_root, force=True)

    installed_text = installed_skill.read_text(encoding="utf-8")
    assert "v2" in installed_text
    assert "local edit" not in installed_text
    source, error = read_installed_skill_source(destination_root / "alpha")
    assert error is None
    assert source is not None
    assert source.installed_commit == updated_commit


def test_install_force_preserves_previous_install_when_staged_replacement_is_invalid(
    tmp_path: Path, monkeypatch
) -> None:
    destination_root = tmp_path / "managed-skills"
    install_dir = destination_root / "alpha"
    install_dir.mkdir(parents=True)
    original_text = "---\nname: alpha\ndescription: Alpha skill\n---\n\nv1\n"
    (install_dir / "SKILL.md").write_text(original_text, encoding="utf-8")

    def fake_populate(_skill: MarketplaceSkill, staged_dir: Path) -> None:
        staged_dir.mkdir(parents=True)
        (staged_dir / "SKILL.md").write_text("---\nname: alpha\n---\n\nbroken\n", encoding="utf-8")

    monkeypatch.setattr(operations, "_populate_marketplace_install_dir", fake_populate)

    try:
        operations.install_marketplace_skill_sync(_marketplace_skill(tmp_path / "repo"), destination_root, force=True)
    except RuntimeError as exc:
        assert "Installed skill could not be reloaded" in str(exc)
    else:
        raise AssertionError("expected forced install to fail")

    assert install_dir.exists()
    assert (install_dir / "SKILL.md").read_text(encoding="utf-8") == original_text


def test_service_install_force_does_not_delete_existing_install_on_reload_failure(tmp_path: Path, monkeypatch) -> None:
    destination_root = tmp_path / "managed-skills"
    install_dir = destination_root / "alpha"
    install_dir.mkdir(parents=True)
    (install_dir / "SKILL.md").write_text("---\nname: alpha\ndescription: Alpha skill\n---\n\nv1\n", encoding="utf-8")
    skill = MarketplaceSkill(
        name="alpha",
        description="Alpha skill",
        repo_url=str(tmp_path / "repo"),
        repo_ref=None,
        repo_path="skills/alpha",
    )

    async def fake_scan_marketplace(_source: str) -> service.MarketplaceScanResult:
        return service.MarketplaceScanResult(source="test", skills=[skill])

    async def fake_install_marketplace_skill(
        _skill: MarketplaceSkill, *, destination_root: Path, force: bool = False
    ) -> Path:
        assert force is True
        return destination_root / _skill.install_dir_name

    def fake_record_from_install_dir(_destination_root: Path, _install_dir: Path) -> service.InstalledSkillRecord:
        raise RuntimeError(f"Installed skill could not be reloaded: {_install_dir}")

    monkeypatch.setattr(service, "scan_marketplace", fake_scan_marketplace)
    monkeypatch.setattr(operations, "install_marketplace_skill", fake_install_marketplace_skill)
    monkeypatch.setattr(service, "_record_from_install_dir", fake_record_from_install_dir)

    try:
        service.install_skill_sync("test", "alpha", destination_root=destination_root, force=True)
    except RuntimeError as exc:
        assert "Installed skill could not be reloaded" in str(exc)
    else:
        raise AssertionError("expected forced install to fail")

    assert install_dir.exists()


def test_install_from_local_repo_honors_repo_ref(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="release")
    release_commit = _commit_all(repo, "initial")
    default_branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    _git(repo, "checkout", "-b", "release")
    _git(repo, "checkout", default_branch)
    _write_skill(repo, body="working tree")
    _commit_all(repo, "update default branch")

    destination_root = tmp_path / "managed-skills"
    install_dir = operations.install_marketplace_skill_sync(
        _marketplace_skill_with_ref(repo, "release"),
        destination_root,
    )

    installed_text = (install_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "release" in installed_text
    assert "working tree" not in installed_text
    source, error = read_installed_skill_source(install_dir)
    assert error is None
    assert source is not None
    assert source.repo_ref == "release"
    assert source.installed_commit == release_commit


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


def test_check_updates_reports_dirty_when_local_skill_is_modified(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")

    destination_root = tmp_path / "managed-skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), destination_root)

    installed_skill = destination_root / "alpha" / "SKILL.md"
    installed_skill.write_text(installed_skill.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")

    updates = service.check_updates(destination_root)

    assert len(updates) == 1
    assert updates[0].status == "dirty"
    assert updates[0].detail == "local modifications detected"


def test_check_updates_many_scans_multiple_skill_roots(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")

    claude_root = tmp_path / ".claude" / "skills"
    codex_root = tmp_path / ".codex" / "skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), claude_root)
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), codex_root)
    (codex_root / ".system").mkdir(parents=True)

    _write_skill(repo, body="v2")
    _commit_all(repo, "update")

    updates = service.check_updates_many([claude_root, codex_root])

    assert len(updates) == 2
    assert [update.index for update in updates] == [1, 2]
    assert [update.status for update in updates] == ["update_available", "update_available"]
    assert [update.skill_dir.parent.parent.name for update in updates] == [".claude", ".codex"]
    assert all(update.name != ".system" for update in updates)


def test_apply_updates_many_updates_matching_name_across_skill_roots(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")

    claude_root = tmp_path / ".claude" / "skills"
    codex_root = tmp_path / ".codex" / "skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), claude_root)
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), codex_root)

    _write_skill(repo, body="v2")
    _commit_all(repo, "update")

    applied = service.apply_updates_many([claude_root, codex_root], "alpha", force=False)

    assert len(applied) == 2
    assert [update.status for update in applied] == ["updated", "updated"]
    assert "v2" in (claude_root / "alpha" / "SKILL.md").read_text(encoding="utf-8")
    assert "v2" in (codex_root / "alpha" / "SKILL.md").read_text(encoding="utf-8")


def test_remove_skill_many_requires_disambiguation_for_duplicate_names(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")

    claude_root = tmp_path / ".claude" / "skills"
    codex_root = tmp_path / ".codex" / "skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), claude_root)
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), codex_root)

    try:
        service.remove_skill_many([claude_root, codex_root], "alpha", remove_all=False)
    except service.AmbiguousSkillError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ambiguous remove to fail")

    assert "Multiple installed skills match 'alpha'" in message
    assert "- alpha in .claude" in message
    assert "- alpha in .codex" in message
    assert (claude_root / "alpha").exists()
    assert (codex_root / "alpha").exists()


def test_remove_skill_many_with_all_removes_all_matching_installs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")

    claude_root = tmp_path / ".claude" / "skills"
    codex_root = tmp_path / ".codex" / "skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), claude_root)
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), codex_root)

    removed = service.remove_skill_many([claude_root, codex_root], "alpha", remove_all=True)

    assert len(removed) == 2
    assert not (claude_root / "alpha").exists()
    assert not (codex_root / "alpha").exists()


def test_list_installed_skills_many_scans_multiple_skill_roots(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")

    claude_root = tmp_path / ".claude" / "skills"
    codex_root = tmp_path / ".codex" / "skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), claude_root)
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), codex_root)

    records = service.list_installed_skills_many([claude_root, codex_root])

    assert len(records) == 2
    assert [record.name for record in records] == ["alpha", "alpha"]
    assert [record.skill_dir.parent.parent.name for record in records] == [".claude", ".codex"]


def test_list_installed_skills_many_dedupes_symlinked_aliases(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")

    shared_root = tmp_path / ".agents" / "skills"
    claude_root = tmp_path / ".claude" / "skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), shared_root)
    claude_root.mkdir(parents=True, exist_ok=True)
    (claude_root / "alpha").symlink_to(shared_root / "alpha", target_is_directory=True)

    records = service.list_installed_skills_many([shared_root, claude_root])

    assert len(records) == 1
    assert records[0].skill_dir == shared_root / "alpha"


def test_list_installed_skills_many_with_aliases_keeps_symlinked_aliases(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")

    shared_root = tmp_path / ".agents" / "skills"
    claude_root = tmp_path / ".claude" / "skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), shared_root)
    claude_root.mkdir(parents=True, exist_ok=True)
    (claude_root / "alpha").symlink_to(shared_root / "alpha", target_is_directory=True)

    records = service.list_installed_skills_many_with_aliases([shared_root, claude_root])

    assert len(records) == 2
    assert records[0].skill_dir == shared_root / "alpha"
    assert records[1].skill_dir == claude_root / "alpha"


def test_check_updates_many_dedupes_symlinked_aliases(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_skill(repo, body="v1")
    _commit_all(repo, "initial")

    shared_root = tmp_path / ".agents" / "skills"
    claude_root = tmp_path / ".claude" / "skills"
    operations.install_marketplace_skill_sync(_marketplace_skill(repo), shared_root)
    claude_root.mkdir(parents=True, exist_ok=True)
    (claude_root / "alpha").symlink_to(shared_root / "alpha", target_is_directory=True)

    updates = service.check_updates_many([shared_root, claude_root])

    assert len(updates) == 1
    assert updates[0].skill_dir == shared_root / "alpha"


def test_remove_skill_many_reports_ambiguity_for_symlinked_aliases(tmp_path: Path) -> None:
    target_root = tmp_path / ".agents" / "skills"
    target_skill = target_root / "alpha"
    target_skill.mkdir(parents=True)
    (target_skill / "SKILL.md").write_text("---\nname: alpha\ndescription: Alpha\n---\n\nbody\n", encoding="utf-8")

    alias_root = tmp_path / ".claude" / "skills"
    alias_root.mkdir(parents=True, exist_ok=True)
    alias_skill = alias_root / "alpha"
    alias_skill.symlink_to(target_skill, target_is_directory=True)

    try:
        service.remove_skill_many([target_root, alias_root], "alpha", remove_all=False)
    except service.AmbiguousSkillError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ambiguous remove to fail")

    assert "- alpha in .agents" in message
    assert "- alpha in .claude" in message
    assert target_skill.exists()
    assert alias_skill.exists()


def test_remove_skill_many_with_all_removes_symlinked_aliases_and_target(tmp_path: Path) -> None:
    target_root = tmp_path / ".agents" / "skills"
    target_skill = target_root / "alpha"
    target_skill.mkdir(parents=True)
    (target_skill / "SKILL.md").write_text("---\nname: alpha\ndescription: Alpha\n---\n\nbody\n", encoding="utf-8")

    alias_root = tmp_path / ".claude" / "skills"
    alias_root.mkdir(parents=True, exist_ok=True)
    alias_skill = alias_root / "alpha"
    alias_skill.symlink_to(target_skill, target_is_directory=True)

    removed = service.remove_skill_many([target_root, alias_root], "alpha", remove_all=True)

    assert len(removed) == 2
    assert not target_skill.exists()
    assert not alias_skill.exists()


def test_remove_local_skill_unlinks_symlink_alias_only(tmp_path: Path) -> None:
    target_root = tmp_path / ".agents" / "skills"
    target_skill = target_root / "alpha"
    target_skill.mkdir(parents=True)
    (target_skill / "SKILL.md").write_text("---\nname: alpha\ndescription: Alpha\n---\n\nbody\n", encoding="utf-8")

    alias_root = tmp_path / ".claude" / "skills"
    alias_root.mkdir(parents=True, exist_ok=True)
    alias_skill = alias_root / "alpha"
    alias_skill.symlink_to(target_skill, target_is_directory=True)

    operations.remove_local_skill(alias_skill, destination_root=alias_root)

    assert not alias_skill.exists()
    assert target_skill.exists()


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
    assert updates[0].status == "dirty"

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
