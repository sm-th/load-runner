# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-02

First release: the loop from [Communication Between Runners and Agents](https://andysmith.ai/2026/Oct/2/communication-between-runners-and-agents/).

### Added

- Bus contract (`start_thread`, `post`, `thread`, `feed`, `threads`) with memory and SQLite adapters ([#11](https://github.com/sm-th/load-runner/pull/11)).
- Runner loop: one thread per run with parameters, batched output, and the result; `::result` lines, process-group timeouts, run numbers continued from the bus ([#12](https://github.com/sm-th/load-runner/pull/12)).
- Thread commands `/stop`, `/restart`, `/set`, `/unset` with acknowledgements, `allow`, and `wait_for_reply` ([#13](https://github.com/sm-th/load-runner/pull/13)).
- Agent bridge that wakes on results and people and pipes the thread to any brain command ([#14](https://github.com/sm-th/load-runner/pull/14)).
- `watch`, `say`, and `threads` for people ([#15](https://github.com/sm-th/load-runner/pull/15)).
- Buzz adapter over the `buzz` CLI ([#16](https://github.com/sm-th/load-runner/pull/16)).
- Zulip adapter over REST ([#17](https://github.com/sm-th/load-runner/pull/17)).
- Presentation video with an original chiptune soundtrack, rendered from source ([#18](https://github.com/sm-th/load-runner/pull/18)).
- README, glossary, ADR 0001, and an offline training example ([#19](https://github.com/sm-th/load-runner/pull/19)).

[0.1.0]: https://github.com/sm-th/load-runner/releases/tag/v0.1.0
