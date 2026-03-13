from __future__ import annotations

import asyncio
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hf_skills.vendor.fast_agent_core import operations
from hf_skills.vendor.fast_agent_core.models import MarketplaceSkill, SkillProvenance, SkillUpdateInfo
from hf_skills.vendor.fast_agent_core.provenance import get_skill_provenance
from hf_skills.vendor.fast_agent_core.registry import SkillManifest, SkillRegistry


class SkillLookupError(LookupError):
    """Raised when a requested marketplace or local skill cannot be resolved."""


class AmbiguousSkillError(LookupError):
    """Raised when a destructive operation matches multiple installed skills."""


@dataclass(frozen=True)
class MarketplaceScanResult:
    source: str
    skills: list[MarketplaceSkill]


@dataclass(frozen=True)
class InstalledSkillRecord:
    name: str
    skill_dir: Path
    manifest: SkillManifest
    provenance: SkillProvenance


@dataclass(frozen=True)
class RemovedSkillRecord:
    name: str
    skill_dir: Path


async def scan_marketplace(source: str) -> MarketplaceScanResult:
    skills, resolved_source = await operations.fetch_marketplace_skills_with_source(source)
    return MarketplaceScanResult(source=resolved_source, skills=skills)


def scan_marketplace_sync(source: str) -> MarketplaceScanResult:
    return asyncio.run(scan_marketplace(source))


def list_installed_skills(destination_root: Path) -> list[InstalledSkillRecord]:
    manifests = SkillRegistry.load_directory(destination_root)
    return [_record_from_manifest(manifest) for manifest in manifests]


def list_installed_skills_many(destination_roots: Sequence[Path]) -> list[InstalledSkillRecord]:
    return _collect_installed_skills_many(destination_roots, dedupe_aliases=True)


def list_installed_skills_many_with_aliases(destination_roots: Sequence[Path]) -> list[InstalledSkillRecord]:
    return _collect_installed_skills_many(destination_roots, dedupe_aliases=False)


def _collect_installed_skills_many(
    destination_roots: Sequence[Path], *, dedupe_aliases: bool
) -> list[InstalledSkillRecord]:
    records: list[InstalledSkillRecord] = []
    seen_dirs: set[Path] = set()
    for destination_root in _unique_destination_roots(destination_roots):
        for record in list_installed_skills(destination_root):
            if dedupe_aliases:
                resolved_skill_dir = record.skill_dir.resolve()
                if resolved_skill_dir in seen_dirs:
                    continue
                seen_dirs.add(resolved_skill_dir)
            records.append(record)
    return records


async def install_skill(
    source: str, selector: str, *, destination_root: Path, force: bool = False
) -> InstalledSkillRecord:
    scan_result = await scan_marketplace(source)
    selected = operations.select_skill_by_name_or_index(scan_result.skills, selector)
    if selected is None:
        raise SkillLookupError(f"Skill not found in marketplace: {selector}")
    install_dir = destination_root.resolve() / selected.install_dir_name
    existed_before = install_dir.exists()
    install_dir = await operations.install_marketplace_skill(selected, destination_root=destination_root, force=force)
    try:
        return _record_from_install_dir(destination_root, install_dir)
    except Exception:
        if install_dir.exists() and not existed_before:
            shutil.rmtree(install_dir)
        raise


def install_skill_sync(
    source: str, selector: str, *, destination_root: Path, force: bool = False
) -> InstalledSkillRecord:
    return asyncio.run(install_skill(source, selector, destination_root=destination_root, force=force))


def remove_skill(destination_root: Path, selector: str) -> RemovedSkillRecord:
    manifests = SkillRegistry.load_directory(destination_root)
    selected = operations.select_manifest_by_name_or_index(manifests, selector)
    if selected is None:
        raise SkillLookupError(f"Installed skill not found: {selector}")
    skill_dir = selected.path.parent if selected.path.is_file() else selected.path
    operations.remove_local_skill(skill_dir, destination_root=destination_root)
    return RemovedSkillRecord(name=selected.name, skill_dir=skill_dir)


def remove_skill_many(
    destination_roots: Sequence[Path], selector: str, *, remove_all: bool
) -> list[RemovedSkillRecord]:
    records = list_installed_skills_many_with_aliases(destination_roots)
    selected = _select_installed_records(records, selector, remove_all=remove_all)
    if not selected:
        raise SkillLookupError(f"Installed skill not found: {selector}")
    removed: list[RemovedSkillRecord] = []
    for record in selected:
        destination_root = record.skill_dir.parent
        operations.remove_local_skill(record.skill_dir, destination_root=destination_root)
        removed.append(RemovedSkillRecord(name=record.name, skill_dir=record.skill_dir))
    return removed


def check_updates(destination_root: Path) -> list[SkillUpdateInfo]:
    return operations.check_skill_updates(destination_root=destination_root)


def apply_updates(destination_root: Path, selector: str, *, force: bool) -> list[SkillUpdateInfo]:
    updates = operations.check_skill_updates(destination_root=destination_root)
    selected = operations.select_skill_updates(updates, selector)
    if not selected:
        raise SkillLookupError(f"Installed skill not found: {selector}")
    return operations.apply_skill_updates(selected, force=force)


def check_updates_many(destination_roots: Sequence[Path]) -> list[SkillUpdateInfo]:
    updates: list[SkillUpdateInfo] = []
    seen_dirs: set[Path] = set()
    for destination_root in _unique_destination_roots(destination_roots):
        for update in operations.check_skill_updates(destination_root=destination_root):
            resolved_skill_dir = update.skill_dir.resolve()
            if resolved_skill_dir in seen_dirs:
                continue
            seen_dirs.add(resolved_skill_dir)
            updates.append(update)
    return _reindex_updates(updates)


def apply_updates_many(destination_roots: Sequence[Path], selector: str, *, force: bool) -> list[SkillUpdateInfo]:
    updates = check_updates_many(destination_roots)
    selected = operations.select_skill_updates(updates, selector)
    if not selected:
        raise SkillLookupError(f"Installed skill not found: {selector}")
    return operations.apply_skill_updates(selected, force=force)


def _record_from_manifest(manifest: SkillManifest) -> InstalledSkillRecord:
    skill_dir = manifest.path.parent if manifest.path.is_file() else manifest.path
    return InstalledSkillRecord(
        name=manifest.name,
        skill_dir=skill_dir,
        manifest=manifest,
        provenance=get_skill_provenance(skill_dir),
    )


def _record_from_install_dir(destination_root: Path, install_dir: Path) -> InstalledSkillRecord:
    for record in list_installed_skills(destination_root):
        if record.skill_dir == install_dir:
            return record
    raise RuntimeError(f"Installed skill could not be reloaded: {install_dir}")


def _select_installed_records(
    records: Sequence[InstalledSkillRecord],
    selector: str,
    *,
    remove_all: bool,
) -> list[InstalledSkillRecord]:
    selector_clean = selector.strip()
    if not selector_clean:
        return []
    if selector_clean.isdigit():
        index = int(selector_clean)
        if 1 <= index <= len(records):
            return [records[index - 1]]
        return []
    selector_lower = selector_clean.lower()
    matches = [record for record in records if record.name.lower() == selector_lower]
    if len(matches) <= 1 or remove_all:
        return matches
    matches_text = "\n".join(
        f"- {record.name} in {_display_skill_root(record.skill_dir)}"
        for record in matches
    )
    raise AmbiguousSkillError(
        "Multiple installed skills match "
        f"'{selector_clean}'. Narrow with --assistant or --target, or rerun with --all.\n{matches_text}"
    )


def _unique_destination_roots(destination_roots: Sequence[Path]) -> list[Path]:
    unique: list[Path] = []
    for root in destination_roots:
        resolved = root.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def _reindex_updates(updates: list[SkillUpdateInfo]) -> list[SkillUpdateInfo]:
    return [
        SkillUpdateInfo(
            index=index,
            name=update.name,
            skill_dir=update.skill_dir,
            status=update.status,
            detail=update.detail,
            current_revision=update.current_revision,
            available_revision=update.available_revision,
            managed_source=update.managed_source,
        )
        for index, update in enumerate(updates, start=1)
    ]


def _display_skill_root(skill_dir: Path) -> str:
    parts = skill_dir.parts
    if len(parts) >= 3 and parts[-2] == "skills":
        return parts[-3]
    return skill_dir.parent.as_posix()
