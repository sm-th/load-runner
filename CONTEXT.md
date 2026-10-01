# load-runner

Mechanical runners, AI agents, and people share one message bus. Each run is a thread; everyone reads it and anyone may steer it.

## Language

**Runner**:
A process that runs a command in a loop by code alone: read the config, open a thread, run, post the result, repeat. Costs no tokens.
_Avoid_: worker, job, executor

**Agent**:
An intelligent participant that sleeps until a result or a person's message wakes it, reads the thread, and replies. Every wake-up costs money.
_Avoid_: bot, assistant, LLM

**Brain**:
The command the agent bridge pipes the thread into (`claude -p`, `codex exec`, a script). The bridge is mechanics; the brain is the intelligence.
_Avoid_: model, backend

**Person**:
A human in the same thread who observes, approves, corrects, or stops.
_Avoid_: user, operator, human-in-the-loop

**Bus**:
The shared place where runners, agents, and people talk: a SQLite file, a Buzz channel, a Zulip stream.
_Avoid_: queue, broker, transport

**Run**:
One execution of the runner's command with one set of parameters.
_Avoid_: job, iteration, build

**Thread**:
All messages about one run: the parameters, output batches, the result, replies, commands, and acknowledgements. It is the audit log.
_Avoid_: topic, conversation, channel

**Command**:
A line in a message that steers the runner: `/stop`, `/restart`, `/set key=value`, `/unset key`.
_Avoid_: directive, instruction

**Override**:
A parameter value set by `/set`. It wins over the config file until `/unset`.
_Avoid_: patch, tweak

**Acknowledgement**:
The runner's message confirming it obeyed or refused a command (`■`, `↻`, `⚙`, `⊘`).
_Avoid_: ack (in prose), receipt
