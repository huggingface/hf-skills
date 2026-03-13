from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Assistant(StrEnum):
    claude = "claude"
    codex = "codex"
    cursor = "cursor"
    opencode = "opencode"


@dataclass(frozen=True)
class TargetResolution:
    selected: Path
    candidates: list[Path]
    mode: str
    reason: str


LOCAL_SHARED_TARGET = Path(".agents/skills")
GLOBAL_SHARED_TARGET = Path("~/.agents/skills")

LOCAL_ASSISTANT_TARGETS = {
    Assistant.claude: Path(".claude/skills"),
    Assistant.codex: Path(".codex/skills"),
    Assistant.cursor: Path(".cursor/skills"),
    Assistant.opencode: Path(".opencode/skills"),
}

GLOBAL_ASSISTANT_TARGETS = {
    Assistant.claude: Path("~/.claude/skills"),
    Assistant.codex: Path("~/.codex/skills"),
    Assistant.cursor: Path("~/.cursor/skills"),
    Assistant.opencode: Path("~/.config/opencode/skills"),
}


def _resolve_path(path: Path, *, cwd: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (cwd / expanded).resolve()


def candidate_targets(*, cwd: Path, global_: bool) -> list[Path]:
    shared_target = GLOBAL_SHARED_TARGET if global_ else LOCAL_SHARED_TARGET
    assistant_targets = GLOBAL_ASSISTANT_TARGETS if global_ else LOCAL_ASSISTANT_TARGETS
    ordered_raw = [shared_target, *assistant_targets.values()]
    ordered: list[Path] = []
    for raw in ordered_raw:
        resolved = _resolve_path(raw, cwd=cwd)
        if resolved not in ordered:
            ordered.append(resolved)
    return ordered


def resolve_target(
    *,
    cwd: Path,
    target: Path | None,
    assistant: Assistant | None,
    global_: bool,
    auto: bool,
) -> TargetResolution:
    if target is not None:
        resolved = _resolve_path(target, cwd=cwd)
        return TargetResolution(
            selected=resolved,
            candidates=[resolved],
            mode="explicit",
            reason="using the directory from --target",
        )

    if assistant is not None:
        mapping = GLOBAL_ASSISTANT_TARGETS if global_ else LOCAL_ASSISTANT_TARGETS
        resolved = _resolve_path(mapping[assistant], cwd=cwd)
        level = "global" if global_ else "project"
        return TargetResolution(
            selected=resolved,
            candidates=[resolved],
            mode="assistant",
            reason=f"using the {level} {assistant.value} skills directory",
        )

    candidates = candidate_targets(cwd=cwd, global_=global_)
    default_target = candidates[0]

    if not auto:
        level = "global" if global_ else "project"
        return TargetResolution(
            selected=default_target,
            candidates=candidates,
            mode="default",
            reason=f"using the default {level} shared skills directory",
        )

    existing = [candidate for candidate in candidates if candidate.exists() and candidate.is_dir()]
    if len(existing) == 1:
        return TargetResolution(
            selected=existing[0],
            candidates=candidates,
            mode="auto",
            reason="found one existing skills directory",
        )

    if len(existing) > 1:
        if default_target in existing:
            return TargetResolution(
                selected=default_target,
                candidates=candidates,
                mode="auto",
                reason="found multiple directories; using the shared .agents/skills directory",
            )
        candidates_text = ", ".join(str(path) for path in existing)
        raise ValueError(
            f"Multiple candidate skills directories found: {candidates_text}. Use --target or --assistant."
        )

    return TargetResolution(
        selected=default_target,
        candidates=candidates,
        mode="auto",
        reason="found no existing directories; using the shared .agents/skills directory",
    )
