# 0001. The thread is the interface

Date: 2026-10-02 · Status: accepted

## Context

A runner, an agent, and a person must coordinate one loop: the runner reports, the agent gives feedback that changes the next run, and the person can see everything and step in at any time ([the article](https://andysmith.ai/2026/Oct/2/communication-between-runners-and-agents/)).

The obvious design is an API: the runner exposes `stop`, `restart`, and `set` endpoints, the agent calls them, and a chat integration mirrors what happened for people. That gives two channels, the API that acts and the chat that describes, and they drift apart. A person reading the chat sees a description of a decision, not the decision.

## Decision

The thread on the bus is the only interface between participants.

- The runner writes plain text with one parseable header line (`✗ train · run 7 failed · exit 1 · 3.1s`).
- Agents and people steer the runner with command lines in ordinary messages (`/set lr=0.03`, `/restart`, `/stop`).
- The runner acknowledges every command in the same thread (`⚙`, `↻`, `■`, `⊘`).

No participant calls another directly. A bus adapter needs only five operations (`start_thread`, `post`, `thread`, `feed`, `threads`), so Buzz, Zulip, and a SQLite file all work.

## Consequences

- The thread is the audit log: every decision and its effect sit next to the output that caused them.
- A person needs nothing beyond the chat app they already use, and their messages reach the agent like any other.
- Commands are text, so anyone allowed in the thread can steer the runner. `allow` narrows that, and commands can change parameters only, never the command line.
- Latency is the bus's polling interval (seconds), which suits CI, monitoring, and training loops, not millisecond control.
- Header lines are a format contract. Changing a glyph or the `name · run N event` shape is a breaking change.
