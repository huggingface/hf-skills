"""Reduced list/table output helpers inspired by huggingface_hub CLI utilities."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

import typer

_MAX_CELL_LENGTH = 48


class OutputFormat(StrEnum):
    table = "table"
    json = "json"


FormatOpt = Annotated[
    OutputFormat,
    typer.Option(help="Output format (table or json)."),
]

QuietOpt = Annotated[
    bool,
    typer.Option("-q", "--quiet", help="Print only IDs (one per line)."),
]


def _to_header(name: str) -> str:
    value = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
    return value.upper()


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, list):
        return ", ".join(_format_value(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _format_cell(value: Any, *, max_len: int = _MAX_CELL_LENGTH) -> str:
    cell = _format_value(value)
    if len(cell) > max_len:
        return cell[: max_len - 3] + "..."
    return cell


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "No results found."
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    header_row = "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    separator = "  ".join("-" * width for width in widths)
    body = ["  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)) for row in rows]
    return "\n".join([header_row, separator, *body])


def print_list_output(
    items: Sequence[dict[str, Any]],
    *,
    format: OutputFormat,
    quiet: bool,
    id_key: str,
    headers: list[str] | None = None,
    row_fn: Callable[[dict[str, Any]], list[str]] | None = None,
) -> None:
    if quiet:
        for item in items:
            print(item[id_key])
        return

    if format == OutputFormat.json:
        print(json.dumps(list(items), indent=2, sort_keys=True))
        return

    if not items:
        print("No results found.")
        return

    resolved_headers = headers or list(items[0].keys())
    resolved_row_fn = row_fn
    if resolved_row_fn is None:

        def resolved_row_fn(item: dict[str, Any]) -> list[str]:
            return [_format_cell(item.get(header)) for header in resolved_headers]

    rendered_headers = [_to_header(header) for header in resolved_headers]
    rendered_rows = [resolved_row_fn(item) for item in items]
    print(_render_table(rendered_headers, rendered_rows))
