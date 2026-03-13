from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from hf_skills.app.config import DEFAULT_REGISTRIES, resolve_registry
from hf_skills.app.presenters import (
    compact_installed_rows,
    compact_update_rows,
    installed_rows,
    marketplace_rows,
    target_rows,
    update_rows,
)
from hf_skills.app.targets import Assistant, TargetResolution, candidate_targets, resolve_target
from hf_skills.vendor.fast_agent_core import service
from hf_skills.vendor.fast_agent_core.registry_urls import format_marketplace_display_url
from hf_skills.vendor.hf_cli_compat.output import FormatOpt, OutputFormat, QuietOpt, print_list_output
from hf_skills.vendor.hf_cli_compat.typer_utils import typer_factory

app = typer_factory(help="Browse, install, and manage skills from the Hugging Face skills marketplace.")

TargetOpt = Annotated[
    Path | None,
    typer.Option("--target", help="Path to the local skills directory to manage."),
]
AssistantOpt = Annotated[
    Assistant | None,
    typer.Option("--assistant", help="Use a known assistant-specific skills directory."),
]
GlobalOpt = Annotated[
    bool,
    typer.Option("--global", "-g", help="Use a user-level target instead of a project-level target."),
]
AutoOpt = Annotated[
    bool,
    typer.Option("--auto", help="Auto-select an existing skills directory, or default to .agents/skills."),
]
RegistryOpt = Annotated[
    str | None,
    typer.Option("--registry", help="Marketplace registry URL, repo URL, or local marketplace.json path."),
]


def _resolve_target_or_exit(
    *,
    target: Path | None,
    assistant: Assistant | None,
    global_: bool,
    auto: bool,
) -> TargetResolution:
    try:
        return resolve_target(
            cwd=Path.cwd(),
            target=target,
            assistant=assistant,
            global_=global_,
            auto=auto,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def _resolve_update_roots(
    *,
    cwd: Path,
    target: Path | None,
    assistant: Assistant | None,
    global_: bool,
    auto: bool,
) -> list[Path]:
    if target is not None or assistant is not None:
        try:
            resolution = resolve_target(
                cwd=cwd,
                target=target,
                assistant=assistant,
                global_=global_,
                auto=auto,
            )
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        return [resolution.selected]
    return candidate_targets(cwd=cwd, global_=global_)


def _resolve_uninstall_roots(
    *,
    cwd: Path,
    target: Path | None,
    assistant: Assistant | None,
    global_: bool,
    auto: bool,
) -> list[Path]:
    return _resolve_update_roots(
        cwd=cwd,
        target=target,
        assistant=assistant,
        global_=global_,
        auto=auto,
    )


def _resolve_installed_roots(
    *,
    cwd: Path,
    target: Path | None,
    assistant: Assistant | None,
    global_: bool,
    auto: bool,
) -> list[Path]:
    return _resolve_update_roots(
        cwd=cwd,
        target=target,
        assistant=assistant,
        global_=global_,
        auto=auto,
    )


def _scan_marketplace_or_exit(source: str) -> service.MarketplaceScanResult:
    try:
        return service.scan_marketplace_sync(source)
    except Exception as exc:
        typer.echo(f"Failed to load marketplace: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _print_marketplace_list(
    *,
    registry: str | None,
    format: OutputFormat,
    quiet: bool,
) -> None:
    source = resolve_registry(registry)
    scan_result = _scan_marketplace_or_exit(source)
    if not quiet and format != OutputFormat.json:
        typer.echo(f"Listing skills from: {format_marketplace_display_url(scan_result.source)}")
    rows = marketplace_rows(scan_result.skills)
    print_list_output(rows, format=format, quiet=quiet, id_key="name")


@app.command(
    "where | target",
    examples=["hf-skills where", "hf-skills where --auto", "hf-skills where --assistant claude"],
)
def where(
    target: TargetOpt = None,
    assistant: AssistantOpt = None,
    global_: GlobalOpt = False,
    auto: AutoOpt = False,
    format: FormatOpt = OutputFormat.table,
    quiet: QuietOpt = False,
) -> None:
    """Show which local skills directory install/remove/update will use."""
    resolution = _resolve_target_or_exit(target=target, assistant=assistant, global_=global_, auto=auto)
    if quiet:
        typer.echo(str(resolution.selected))
        return

    affects = ["install", "installed", "uninstall", "update"]
    if format == OutputFormat.json:
        payload = {
            "skills_directory": str(resolution.selected),
            "why": resolution.reason,
            "affects": affects,
            "checked": [str(candidate) for candidate in resolution.candidates],
        }
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"Using skills directory: {resolution.selected}")
    typer.echo(f"Why: {resolution.reason}")
    typer.echo(f"Affects: {', '.join(affects)}")
    typer.echo("")
    typer.echo("To use a different directory:")
    typer.echo("  hf-skills where --target /path/to/skills")
    typer.echo("  hf-skills where --assistant claude")
    typer.echo("  hf-skills where --global")

    if resolution.candidates:
        typer.echo("")
        typer.echo("Checked locations:")
        rows = target_rows(candidates=resolution.candidates, selected=resolution.selected, reason=resolution.reason)
        print_list_output(rows, format=OutputFormat.table, quiet=False, id_key="path")


@app.command(
    "list | ls",
    examples=["hf-skills list", "hf-skills list --registry ./marketplace.json"],
)
def list_marketplace(
    registry: RegistryOpt = None,
    format: FormatOpt = OutputFormat.table,
    quiet: QuietOpt = False,
) -> None:
    """List skills available from the configured registry."""
    _print_marketplace_list(registry=registry, format=format, quiet=quiet)


@app.command(
    "available",
    examples=["hf-skills available", "hf-skills available --registry ./marketplace.json"],
    hidden=True,
)
def available(
    registry: RegistryOpt = None,
    format: FormatOpt = OutputFormat.table,
    quiet: QuietOpt = False,
) -> None:
    """Backward-compatible alias for `hf-skills list`."""
    _print_marketplace_list(registry=registry, format=format, quiet=quiet)


@app.command(
    "installed",
    examples=["hf-skills installed", "hf-skills installed --target .claude/skills"],
)
def installed(
    target: TargetOpt = None,
    assistant: AssistantOpt = None,
    global_: GlobalOpt = False,
    auto: AutoOpt = False,
    format: FormatOpt = OutputFormat.table,
    quiet: QuietOpt = False,
) -> None:
    """List installed skills across known directories, or a specific one when narrowed."""
    installed_roots = _resolve_installed_roots(
        cwd=Path.cwd(),
        target=target,
        assistant=assistant,
        global_=global_,
        auto=auto,
    )
    records = service.list_installed_skills_many_with_aliases(installed_roots)
    rows = installed_rows(records, cwd=Path.cwd()) if format == OutputFormat.json else compact_installed_rows(records)
    print_list_output(rows, format=format, quiet=quiet, id_key="name")


@app.command(
    "search",
    examples=["hf-skills search dataset", "hf-skills search gradio --registry ./marketplace.json"],
)
def search(
    query: Annotated[str, typer.Argument(help="Search query.")],
    registry: RegistryOpt = None,
    format: FormatOpt = OutputFormat.table,
    quiet: QuietOpt = False,
) -> None:
    """Search registry skills by name or description."""
    source = resolve_registry(registry)
    scan_result = _scan_marketplace_or_exit(source)
    tokens = [token.casefold() for token in query.split() if token.strip()]
    filtered = [
        skill
        for skill in scan_result.skills
        if all(
            token
            in " ".join(
                part.casefold()
                for part in [
                    skill.name,
                    skill.description or "",
                    skill.bundle_name or "",
                    skill.bundle_description or "",
                ]
            )
            for token in tokens
        )
    ]
    if not quiet and format != OutputFormat.json:
        typer.echo(f"Listing skills from: {format_marketplace_display_url(scan_result.source)}")
    rows = marketplace_rows(filtered)
    print_list_output(rows, format=format, quiet=quiet, id_key="name")


@app.command(
    "install | add",
    examples=[
        "hf-skills install hf-cli",
        "hf-skills install 1 --auto",
        "hf-skills install gradio --assistant claude",
    ],
)
def install(
    selector: Annotated[str, typer.Argument(help="Skill name or marketplace index.")],
    target: TargetOpt = None,
    assistant: AssistantOpt = None,
    global_: GlobalOpt = False,
    auto: AutoOpt = False,
    registry: RegistryOpt = None,
    force: Annotated[
        bool,
        typer.Option("--force", "--update", help="Overwrite an existing install at the selected target."),
    ] = False,
) -> None:
    """Install a registry skill into the selected target directory."""
    resolution = _resolve_target_or_exit(target=target, assistant=assistant, global_=global_, auto=auto)
    source = resolve_registry(registry)
    try:
        record = service.install_skill_sync(source, selector, destination_root=resolution.selected, force=force)
    except (json.JSONDecodeError, service.SkillLookupError, FileExistsError, FileNotFoundError, RuntimeError) as exc:
        if isinstance(exc, FileExistsError):
            typer.echo(f"{exc}\nRe-run with --force to overwrite.", err=True)
        else:
            typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Installed '{record.name}' to {record.skill_dir}")


@app.command(
    "uninstall | remove | rm",
    examples=["hf-skills uninstall hf-cli", "hf-skills rm 1 --target .agents/skills"],
)
def uninstall(
    selector: Annotated[str, typer.Argument(help="Installed skill name or index.")],
    target: TargetOpt = None,
    assistant: AssistantOpt = None,
    global_: GlobalOpt = False,
    auto: AutoOpt = False,
    all_: Annotated[
        bool,
        typer.Option("--all", help="Remove all matching installs across scanned skill roots."),
    ] = False,
) -> None:
    """Remove an installed skill, scanning known directories unless narrowed."""
    uninstall_roots = _resolve_uninstall_roots(
        cwd=Path.cwd(),
        target=target,
        assistant=assistant,
        global_=global_,
        auto=auto,
    )
    try:
        removed = service.remove_skill_many(uninstall_roots, selector, remove_all=all_)
    except (service.AmbiguousSkillError, service.SkillLookupError, FileNotFoundError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    for record in removed:
        typer.echo(f"Removed '{record.name}' from {record.skill_dir}")


@app.command(
    "update",
    examples=["hf-skills update", "hf-skills update all --force", "hf-skills update hf-cli --target .agents/skills"],
)
def update(
    selector: Annotated[
        str,
        typer.Argument(help="Installed skill name, index, or 'all'."),
    ] = "all",
    target: TargetOpt = None,
    assistant: AssistantOpt = None,
    global_: GlobalOpt = False,
    auto: AutoOpt = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite local changes when updating.")] = False,
    format: FormatOpt = OutputFormat.table,
    quiet: QuietOpt = False,
) -> None:
    """Update installed skills across known directories, or a specific one when narrowed."""
    update_roots = _resolve_update_roots(
        cwd=Path.cwd(),
        target=target,
        assistant=assistant,
        global_=global_,
        auto=auto,
    )
    try:
        updates = service.apply_updates_many(update_roots, selector, force=force)
    except service.SkillLookupError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    rows = update_rows(updates, cwd=Path.cwd()) if format == OutputFormat.json else compact_update_rows(updates)
    print_list_output(rows, format=format, quiet=quiet, id_key="name")


@app.command("registries", topic="help")
def registries() -> None:
    """Print built-in marketplace registry defaults."""
    for url in DEFAULT_REGISTRIES:
        typer.echo(format_marketplace_display_url(url))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
