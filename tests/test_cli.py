from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from hf_skills.cli.main import app

runner = CliRunner()


def _create_skill_repo(root: Path, *, name: str, description: str) -> Path:
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    marketplace = root / ".claude-plugin" / "marketplace.json"
    marketplace.parent.mkdir(parents=True, exist_ok=True)
    marketplace.write_text(
        json.dumps(
            {
                "plugins": [
                    {
                        "name": name,
                        "source": f"./skills/{name}",
                        "skills": "./",
                        "description": description,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return marketplace


def test_available_lists_marketplace_skill(tmp_path: Path) -> None:
    marketplace = _create_skill_repo(tmp_path / "repo", name="alpha", description="Alpha skill")
    result = runner.invoke(app, ["available", "--registry", marketplace.as_posix()])
    assert result.exit_code == 0
    assert "alpha" in result.stdout
    assert "Alpha skill" in result.stdout


def test_add_then_list_installed_skill(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    marketplace = _create_skill_repo(repo_root, name="alpha", description="Alpha skill")
    target = tmp_path / "managed-skills"
    add_result = runner.invoke(
        app,
        ["install", "alpha", "--registry", marketplace.as_posix(), "--target", target.as_posix()],
    )
    assert add_result.exit_code == 0
    assert (target / "alpha" / "SKILL.md").exists()

    list_result = runner.invoke(app, ["installed", "--target", target.as_posix()])
    assert list_result.exit_code == 0
    assert "alpha" in list_result.stdout


def test_install_reports_force_hint_when_skill_exists(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    marketplace = _create_skill_repo(repo_root, name="alpha", description="Alpha skill")
    target = tmp_path / "managed-skills"

    first_result = runner.invoke(
        app,
        ["install", "alpha", "--registry", marketplace.as_posix(), "--target", target.as_posix()],
    )
    assert first_result.exit_code == 0

    second_result = runner.invoke(
        app,
        ["install", "alpha", "--registry", marketplace.as_posix(), "--target", target.as_posix()],
    )

    assert second_result.exit_code == 1
    assert "Skill already exists:" in second_result.stderr
    assert "Re-run with --force to overwrite." in second_result.stderr


def test_install_force_overwrites_existing_skill(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    marketplace = _create_skill_repo(repo_root, name="alpha", description="Alpha skill")
    target = tmp_path / "managed-skills"

    first_result = runner.invoke(
        app,
        ["install", "alpha", "--registry", marketplace.as_posix(), "--target", target.as_posix()],
    )
    assert first_result.exit_code == 0

    skill_file = target / "alpha" / "SKILL.md"
    skill_file.write_text("---\nname: alpha\ndescription: Local override\n---\n\nlocal\n", encoding="utf-8")

    force_result = runner.invoke(
        app,
        ["install", "alpha", "--registry", marketplace.as_posix(), "--target", target.as_posix(), "--force"],
    )

    assert force_result.exit_code == 0
    installed_text = skill_file.read_text(encoding="utf-8")
    assert "Alpha skill" in installed_text
    assert "Local override" not in installed_text


def test_install_update_alias_overwrites_existing_skill(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    marketplace = _create_skill_repo(repo_root, name="alpha", description="Alpha skill")
    target = tmp_path / "managed-skills"

    first_result = runner.invoke(
        app,
        ["install", "alpha", "--registry", marketplace.as_posix(), "--target", target.as_posix()],
    )
    assert first_result.exit_code == 0

    skill_file = target / "alpha" / "SKILL.md"
    skill_file.write_text("---\nname: alpha\ndescription: Local override\n---\n\nlocal\n", encoding="utf-8")

    update_result = runner.invoke(
        app,
        ["install", "alpha", "--registry", marketplace.as_posix(), "--target", target.as_posix(), "--update"],
    )

    assert update_result.exit_code == 0
    installed_text = skill_file.read_text(encoding="utf-8")
    assert "Alpha skill" in installed_text
    assert "Local override" not in installed_text


def test_where_auto_prefers_existing_shared_agents_directory(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cwd = Path.cwd()
    try:
        os.chdir(project_dir)
        (project_dir / ".agents" / "skills").mkdir(parents=True)
        result = runner.invoke(app, ["target", "--auto"])
    finally:
        os.chdir(cwd)

    assert result.exit_code == 0
    assert "Using skills directory:" in result.stdout
    assert "Affects: install, installed, uninstall, update" in result.stdout
    assert "Checked locations:" in result.stdout
    assert ".agents/skills" in result.stdout


def test_remove_deletes_installed_skill(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    marketplace = _create_skill_repo(repo_root, name="alpha", description="Alpha skill")
    target = tmp_path / "managed-skills"
    add_result = runner.invoke(
        app,
        ["install", "alpha", "--registry", marketplace.as_posix(), "--target", target.as_posix()],
    )
    assert add_result.exit_code == 0

    remove_result = runner.invoke(app, ["uninstall", "alpha", "--target", target.as_posix()])
    assert remove_result.exit_code == 0
    assert not (target / "alpha").exists()


def test_list_alias_lists_marketplace_skill(tmp_path: Path) -> None:
    marketplace = _create_skill_repo(tmp_path / "repo", name="alpha", description="Alpha skill")
    result = runner.invoke(app, ["list", "--registry", marketplace.as_posix()])
    assert result.exit_code == 0
    assert "Listing skills from:" in result.stdout
    assert "alpha" in result.stdout
    assert "Alpha skill" in result.stdout
    assert "SOURCE" not in result.stdout
    assert "PATH" not in result.stdout


def test_list_json_suppresses_marketplace_banner(tmp_path: Path) -> None:
    marketplace = _create_skill_repo(tmp_path / "repo", name="alpha", description="Alpha skill")

    result = runner.invoke(app, ["list", "--registry", marketplace.as_posix(), "--format", "json"])

    assert result.exit_code == 0
    assert "Listing skills from:" not in result.stdout
    assert json.loads(result.stdout) == [
        {
            "description": "Alpha skill",
            "index": "1",
            "name": "alpha",
        }
    ]


def test_list_reports_invalid_marketplace_json_cleanly(tmp_path: Path) -> None:
    marketplace = tmp_path / "marketplace.json"
    marketplace.write_text("{ invalid", encoding="utf-8")

    result = runner.invoke(app, ["list", "--registry", marketplace.as_posix()])

    assert result.exit_code == 1
    assert "Failed to load marketplace:" in result.stderr
    assert "JSONDecodeError" not in result.stderr


def test_search_quiet_suppresses_marketplace_banner(tmp_path: Path) -> None:
    marketplace = _create_skill_repo(tmp_path / "repo", name="alpha", description="Alpha skill")

    result = runner.invoke(app, ["search", "alpha", "--registry", marketplace.as_posix(), "--quiet"])

    assert result.exit_code == 0
    assert "Listing skills from:" not in result.stdout
    assert result.stdout.strip().splitlines() == ["alpha"]
