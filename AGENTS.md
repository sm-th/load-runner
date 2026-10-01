# load-runner

Mechanical runners, AI agents, and people in one thread. Glossary: [CONTEXT.md](CONTEXT.md). Why the thread is the interface: [ADR 0001](docs/adr/0001-the-thread-is-the-interface.md).

## Module seams

Keep them deep: callers never see platform APIs.

- `bus/`: the `Bus` contract (`start_thread`, `post`, `thread`, `feed`, `threads`) and one module per adapter. Platform details stay inside the adapter.
- `protocol`: the only place that knows header lines, glyphs, and command syntax.
- `runner`: the loop and process control. No platform code, no intelligence.
- `agent`: wake rules and the brain call. No platform code.
- `watch`, `cli`: the surface for people.
- `config`: TOML in, dataclasses out. Secrets come from the environment only.

## Invariants

- Every change of runner state is a message in the thread (start, output, result, acknowledgement).
- The runner never obeys a message that parses as a runner header.
- `/set` changes parameters, never the command line.
- The agent never wakes on its own messages and stops after `max_replies` per thread.
- Zero runtime dependencies.

## Checks

```sh
uv run ruff check && uv run ruff format --check && uv run pytest -q
```

New adapters join the shared contract suite in `tests/test_bus_contract.py` via the `connect` fixture.
