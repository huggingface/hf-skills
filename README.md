# hf-skills

Standalone Hugging Face skills installer CLI.

## Why include a Manifest?

The [agentskills.io](https://agentskills.io) spec doesn't require a version in the frontmatter. When version numbers are included, they often aren't updated as the skill changes. A small manifest describing the source commit (local or remote) makes auto-updating simple!

## Commands

```bash
uv run hf-skills --help
uv run hf-skills list
uv run hf-skills search gradio
uv run hf-skills where --auto
uv run hf-skills install hf-cli --auto
uv run hf-skills installed --target .agents/skills
```

## Development

```bash
uv sync --dev
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
```

