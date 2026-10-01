# Contributing

## Setup

```sh
uv sync
uv run pytest -q
```

Python 3.12+ and [uv](https://docs.astral.sh/uv/). The package has no runtime dependencies; keep it that way unless an adapter truly needs one.

## Workflow

1. Open an issue first (bug or feature form). Describe behavior as messages in a thread when you can.
2. Branch from `main`: `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>`, `chore/<short-name>`.
3. Commit with [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat(runner): stream output in batches`
   - `fix(bus): keep message order stable in SQLite`
   - `docs: explain control commands`
   - `chore(ci): pin uv`
   Scopes: `bus`, `runner`, `agent`, `cli`, `buzz`, `zulip`, `video`, `ci`.
4. Open a pull request that closes the issue. CI runs `ruff check`, `ruff format --check`, and `pytest` on Python 3.12 and 3.13.
5. Pull requests are squash-merged; the PR title becomes the commit on `main`, so it must be a Conventional Commit too.

## Before you push

```sh
uv run ruff check
uv run ruff format --check
uv run pytest -q
```

## Tests

Test what a person or an agent would observe in the thread: messages, their order, and what the runner does after a command. Do not assert wiring or private fields.
