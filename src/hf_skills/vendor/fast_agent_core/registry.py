from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import frontmatter


@dataclass(frozen=True)
class SkillManifest:
    name: str
    description: str
    body: str
    path: Path
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] | None = None
    allowed_tools: list[str] | None = None


class SkillRegistry:
    @classmethod
    def load_directory(cls, directory: Path) -> list[SkillManifest]:
        if not directory.exists() or not directory.is_dir():
            return []
        return cls._load_directory(directory)

    @classmethod
    def load_directory_with_errors(cls, directory: Path) -> tuple[list[SkillManifest], list[dict[str, str]]]:
        errors: list[dict[str, str]] = []
        manifests = cls._load_directory(directory, errors)
        return manifests, errors

    @classmethod
    def _load_directory(
        cls,
        directory: Path,
        errors: list[dict[str, str]] | None = None,
    ) -> list[SkillManifest]:
        manifests: list[SkillManifest] = []
        for entry in sorted(directory.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "SKILL.md"
            if not manifest_path.exists():
                continue
            manifest, error = cls._parse_manifest(manifest_path)
            if manifest is not None:
                manifests.append(manifest)
            elif errors is not None:
                errors.append({"path": str(manifest_path), "error": error or "Failed to parse skill manifest"})
        return manifests

    @classmethod
    def _parse_manifest(cls, manifest_path: Path) -> tuple[SkillManifest | None, str | None]:
        try:
            manifest_text = manifest_path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)
        return cls.parse_manifest_text(manifest_text, path=manifest_path)

    @classmethod
    def parse_manifest_text(
        cls,
        manifest_text: str,
        *,
        path: Path | None = None,
    ) -> tuple[SkillManifest | None, str | None]:
        manifest_path = path or Path("<in-memory>")
        try:
            post = frontmatter.loads(manifest_text)
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)
        metadata = post.metadata or {}
        name = metadata.get("name")
        description = metadata.get("description")
        if not isinstance(name, str) or not name.strip():
            return None, "Missing 'name' field"
        if not isinstance(description, str) or not description.strip():
            return None, "Missing 'description' field"
        allowed_tools_raw = metadata.get("allowed-tools")
        allowed_tools: list[str] | None = None
        if isinstance(allowed_tools_raw, str) and allowed_tools_raw.strip():
            allowed_tools = allowed_tools_raw.split()
        typed_metadata: dict[str, str] | None = None
        custom_metadata = metadata.get("metadata")
        if isinstance(custom_metadata, dict):
            typed_metadata = {str(key): str(value) for key, value in custom_metadata.items()}
        license_value = metadata.get("license")
        license_text = license_value if isinstance(license_value, str) else None
        compatibility_value = metadata.get("compatibility")
        compatibility_text = compatibility_value if isinstance(compatibility_value, str) else None
        return (
            SkillManifest(
                name=name.strip(),
                description=description.strip(),
                body=(post.content or "").strip(),
                path=manifest_path,
                license=license_text,
                compatibility=compatibility_text,
                metadata=typed_metadata,
                allowed_tools=allowed_tools,
            ),
            None,
        )
