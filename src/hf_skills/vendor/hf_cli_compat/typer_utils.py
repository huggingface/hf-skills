"""Reduced CLI helpers derived from huggingface_hub's Typer setup."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Literal

import click
import typer
import typer.core

CLI_REFERENCE_URL = "https://huggingface.co/docs/huggingface_hub/en/guides/cli"
TOPIC_T = Literal["main", "help"] | str
_ALIAS_SPLIT = re.compile(r"\s*\|\s*")


def generate_epilog(examples: list[str], docs_anchor: str | None = None) -> str:
    docs_url = f"{CLI_REFERENCE_URL}{docs_anchor}" if docs_anchor else CLI_REFERENCE_URL
    examples_str = "\n".join(f"  $ {example}" for example in examples)
    return (
        f"Examples\n{examples_str}\n\n"
        "Learn more\n"
        "  Use `hf-skills <command> --help` for more information about a command.\n"
        f"  Read the documentation at {docs_url}\n"
    )


def _format_epilog_no_indent(epilog: str | None, ctx: click.Context, formatter: click.HelpFormatter) -> None:
    del ctx
    if epilog:
        formatter.write_paragraph()
        for line in epilog.split("\n"):
            formatter.write_text(line)


class HFCliTyperGroup(typer.core.TyperGroup):
    """Typer group with aliases and `hf`-style sectioned help."""

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command
        for registered_name, registered_command in self.commands.items():
            aliases = _ALIAS_SPLIT.split(registered_name)
            if cmd_name in aliases:
                return registered_command
        return None

    def _alias_map(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for registered_name in self.commands:
            parts = _ALIAS_SPLIT.split(registered_name)
            result[parts[0]] = parts[1:]
        return result

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        topics: dict[str, list[tuple[str, str]]] = {}
        alias_map = self._alias_map()
        for name in self.list_commands(ctx):
            command = self.get_command(ctx, name)
            if command is None or command.hidden:
                continue
            help_text = command.get_short_help_str(limit=formatter.width)
            aliases = alias_map.get(name, [])
            if aliases:
                help_text = f"{help_text} [alias: {', '.join(aliases)}]"
            topic = getattr(command, "topic", "main")
            topics.setdefault(topic, []).append((name, help_text))

        with formatter.section("Main commands"):
            formatter.write_dl(topics.get("main", []))
        for topic in sorted(topics):
            if topic == "main":
                continue
            with formatter.section(f"{topic.capitalize()} commands"):
                formatter.write_dl(topics[topic])

    def format_epilog(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        all_examples: list[str] = []
        for name in self.list_commands(ctx):
            command = self.get_command(ctx, name)
            if command is None or command.hidden:
                continue
            examples = getattr(command, "examples", [])
            if examples:
                all_examples.append(examples[0])
        if all_examples:
            _format_epilog_no_indent(generate_epilog(all_examples), ctx, formatter)
        elif self.epilog:
            _format_epilog_no_indent(self.epilog, ctx, formatter)

    def list_commands(self, ctx: click.Context) -> list[str]:
        del ctx
        primary_names = []
        for name in self.commands:
            primary_names.append(_ALIAS_SPLIT.split(name)[0])
        return sorted(primary_names)


def _hf_cli_command(topic: TOPIC_T, examples: list[str] | None = None) -> type[typer.core.TyperCommand]:
    def format_epilog(self: click.Command, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        _format_epilog_no_indent(self.epilog, ctx, formatter)

    return type(
        f"TyperCommand{topic.capitalize()}",
        (typer.core.TyperCommand,),
        {"topic": topic, "examples": examples or [], "format_epilog": format_epilog},
    )


class HFCliApp(typer.Typer):
    def command(  # type: ignore[override]
        self,
        name: str | None = None,
        *,
        topic: TOPIC_T = "main",
        examples: list[str] | None = None,
        context_settings: dict[str, Any] | None = None,
        help: str | None = None,
        epilog: str | None = None,
        short_help: str | None = None,
        options_metavar: str = "[OPTIONS]",
        add_help_option: bool = True,
        no_args_is_help: bool = False,
        hidden: bool = False,
        deprecated: bool = False,
        rich_help_panel: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        if epilog is None and examples:
            epilog = generate_epilog(examples)

        def _inner(func: Callable[..., Any]) -> Callable[..., Any]:
            return super(HFCliApp, self).command(
                name,
                cls=_hf_cli_command(topic, examples),
                context_settings=context_settings,
                help=help,
                epilog=epilog,
                short_help=short_help,
                options_metavar=options_metavar,
                add_help_option=add_help_option,
                no_args_is_help=no_args_is_help,
                hidden=hidden,
                deprecated=deprecated,
                rich_help_panel=rich_help_panel,
            )(func)

        return _inner


def typer_factory(help: str, epilog: str | None = None) -> HFCliApp:
    return HFCliApp(
        help=help,
        epilog=epilog,
        add_completion=True,
        no_args_is_help=True,
        cls=HFCliTyperGroup,
        rich_markup_mode=None,
        rich_help_panel=None,
        pretty_exceptions_enable=False,
        context_settings={
            "max_content_width": 120,
            "help_option_names": ["-h", "--help"],
        },
    )
