from __future__ import annotations

from pathlib import Path

from hf_skills.app.targets import Assistant, candidate_targets
from hf_skills.cli.main import _resolve_installed_roots, _resolve_update_roots


def test_resolve_update_roots_scans_known_targets_by_default(tmp_path: Path) -> None:
    roots = _resolve_update_roots(
        cwd=tmp_path,
        target=None,
        assistant=None,
        global_=False,
        auto=False,
    )

    assert roots == candidate_targets(cwd=tmp_path, global_=False)


def test_resolve_update_roots_respects_explicit_target(tmp_path: Path) -> None:
    target = tmp_path / "custom-skills"

    roots = _resolve_update_roots(
        cwd=tmp_path,
        target=target,
        assistant=None,
        global_=False,
        auto=False,
    )

    assert roots == [target.resolve()]


def test_resolve_update_roots_respects_assistant_target(tmp_path: Path) -> None:
    roots = _resolve_update_roots(
        cwd=tmp_path,
        target=None,
        assistant=Assistant.codex,
        global_=False,
        auto=False,
    )

    assert roots == [(tmp_path / ".codex" / "skills").resolve()]


def test_resolve_installed_roots_scans_known_targets_by_default(tmp_path: Path) -> None:
    roots = _resolve_installed_roots(
        cwd=tmp_path,
        target=None,
        assistant=None,
        global_=False,
        auto=False,
    )

    assert roots == candidate_targets(cwd=tmp_path, global_=False)
