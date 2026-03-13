from __future__ import annotations

from pathlib import Path

from hf_skills.vendor.fast_agent_core import provenance
from hf_skills.vendor.fast_agent_core.models import MarketplaceSkill, SkillUpdateInfo
from hf_skills.vendor.fast_agent_core.service import InstalledSkillRecord


def marketplace_rows(skills: list[MarketplaceSkill]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, skill in enumerate(skills, start=1):
        rows.append(
            {
                "index": str(index),
                "name": skill.name,
                "description": skill.description or "",
            }
        )
    return rows


def installed_rows(records: list[InstalledSkillRecord], *, cwd: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, record in enumerate(records, start=1):
        relative_path = _display_path(record.skill_dir, cwd=cwd)
        provenance_value, installed_value = provenance.format_skill_provenance_details(record.skill_dir)
        rows.append(
            {
                "index": str(index),
                "name": record.name,
                "location": relative_path,
                "provenance": provenance_value,
                "installed": installed_value or "",
            }
        )
    return rows


def update_rows(updates: list[SkillUpdateInfo], *, cwd: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for update in updates:
        rows.append(
            {
                "index": str(update.index),
                "name": update.name,
                "status": update.status,
                "location": _display_path(update.skill_dir, cwd=cwd),
                "current": update.current_revision or "",
                "available": update.available_revision or "",
                "detail": update.detail or "",
            }
        )
    return rows


def target_rows(*, candidates: list[Path], selected: Path, reason: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for candidate in candidates:
        note = "selected" if candidate == selected else "checked"
        rows.append(
            {
                "path": str(candidate),
                "exists": "yes" if candidate.exists() and candidate.is_dir() else "",
                "selected": "yes" if candidate == selected else "",
                "note": note,
            }
        )
    if not rows:
        rows.append(
            {
                "path": str(selected),
                "exists": "yes" if selected.exists() and selected.is_dir() else "",
                "selected": "yes",
                "note": "selected",
            }
        )
    return rows


def _display_path(path: Path, *, cwd: Path) -> str:
    try:
        return path.relative_to(cwd).as_posix()
    except ValueError:
        return path.as_posix()
