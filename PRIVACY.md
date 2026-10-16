# Privacy

broken-rules runs on your machine and keeps everything in your repo.

## What it reads
- `BROKEN-RULES.md`, the register.
- The instruction files listed under `sources` in the register (for example AGENTS.md,
  CLAUDE.md and SKILL.md files), to find the rule you quote.
- Git history, to check that a fix commit is in HEAD's history.
- Two environment variables: `BROKEN_RULES_FILE` (an optional register path) and
  `CLAUDE_PROJECT_DIR` (the project folder, set by the agent).

## What it writes
- `BROKEN-RULES.md` only.

## What it runs
- The check commands in your register, as shell commands, from the register's folder. You or
  your agent write them; review them like any script in your repo.

## What it sends
- Nothing. The plugin makes no network calls, collects no data and has no telemetry. A check
  command you write could use the network (for example `git fetch`); that is your command.

## Contact
Questions: [GitHub issues](https://github.com/S3yon/broken-rules/issues).
