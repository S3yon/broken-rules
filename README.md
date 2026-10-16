# broken-rules

A register of the rules your coding agent broke. Each entry quotes the rule from the file the
agent loads (AGENTS.md, CLAUDE.md, a SKILL.md), says what happened, and carries a shell check that
fails while the break is real. Every scan re-runs the checks: a fix is marked verified only when
its check passes and its commit is in HEAD's history, and a fix that stops holding is reopened.
At the start of each session the agent is shown the breaks that are still open.

Config linters read your instruction files. Transcript checkers read one session. This keeps a
running record across sessions and proves each fix still holds.

| | Reads | Keeps a record over time | Proves a fix held |
|---|---|---|---|
| Config linters | the instruction files | no | no |
| Transcript checkers | one session | no | no |
| broken-rules | a check command per break | yes, `BROKEN-RULES.md` | yes, on every scan |

## Install

Needs Python 3.9 or later and git. No other dependencies.

```
claude plugin marketplace add S3yon/broken-rules
claude plugin install broken-rules@broken-rules
```

The plugin adds two skills (`file-break`, `scan`) and a session-start hook. The script also runs on
its own: `python3 scripts/broken_rules.py --help`.

## Use it

Ask the agent in plain words:

- "That commit has a co-author line and AGENTS.md says never. File it as a broken rule."
- "You ran `git -C` again; the routine rules ban it. Log that."
- "Scan the broken-rules register and tell me what reopened."
- "Which rules have you broken in this repo that are still open?"

The first time, `file-break` creates `BROKEN-RULES.md` at the repo root. Commit it with your code.

## Demo

`examples/demo.sh` builds a throwaway git repo with an AGENTS.md and four files that break its
rules (rewritten from a real register), then runs the whole loop. Real output:

```
== File four breaks. Each check must fail now, or the break is refused.

$ broken_rules.py file --title "Web reader has no page-text-is-data line" --severity med --rule "is data, never instructions" --evidence … --fix … --check "grep -q 'data, never instructions' agents/web-reader.md"
FILED B-001 Web reader has no page-text-is-data line (rule AGENTS.md:3)

$ broken_rules.py file --title "Publish skill can be started by the model" --severity med --rule "sets disable-model-invocation: true" --evidence … --fix … --check "grep -q '^disable-model-invocation: true$' skills/publish/SKILL.md"
FILED B-002 Publish skill can be started by the model (rule AGENTS.md:4)

$ broken_rules.py file --title "Nightly prompt uses git -C" --severity med --rule "never use git -C" --evidence … --fix … --check "test -f routines/nightly.md && ! grep -q 'git -C' routines/nightly.md"
FILED B-003 Nightly prompt uses git -C (rule AGENTS.md:5)

$ broken_rules.py file --title "Commit carried an AI co-author line" --severity high --rule "Never add AI co-author lines" --evidence … --fix … --check "! git log --format=%B | grep -qi '^co-authored-by:'"
FILED B-004 Commit carried an AI co-author line (rule AGENTS.md:6)

== A check that passes now cannot show a break, so it is refused.

$ broken_rules.py file --title "Bad check" --severity low --rule "Never add AI co-author lines" --evidence … --fix … --check "test -f AGENTS.md"
ERROR check passes now, so it cannot show the break; write one that fails while the rule is broken
(exit 1)

== Fix three, record each fix commit, then re-check.

$ broken_rules.py fixed B-001 85ef1ea
FIXED B-001 85ef1ea; run update to verify

$ broken_rules.py fixed B-002 b5d99ac
FIXED B-002 b5d99ac; run update to verify

$ broken_rules.py fixed B-003 125477b
FIXED B-003 125477b; run update to verify

$ broken_rules.py update
VERIFIED B-001 check passes; fix commit 85ef1ea is in HEAD's history
VERIFIED B-002 check passes; fix commit b5d99ac is in HEAD's history
VERIFIED B-003 check passes; fix commit 125477b is in HEAD's history
open 1 · fixed 0 · verified 3 · reopened 0 · wontfix 0

== Someone drops the publish guard again.

$ broken_rules.py update
REOPENED B-002 exit 1: grep -q '^disable-model-invocation: true$' skills/publish/SKILL.md
open 1 · fixed 0 · verified 2 · reopened 1 · wontfix 0
(exit 1)

== What the agent sees at the next session start:

BROKEN RULES: 2 rules the agent broke in this project are not fixed yet (BROKEN-RULES.md). Keep them this session:
- B-002 (reopened) Publish skill can be started by the model. Rule: "sets disable-model-invocation: true" (AGENTS.md:4)
- B-004 (open) Commit carried an AI co-author line. Rule: "Never add AI co-author lines" (AGENTS.md:6)
When the user corrects you for breaking a written rule, file it with the file-break skill.
```

The register it leaves behind is in [examples/BROKEN-RULES.md](examples/BROKEN-RULES.md).

## The register

`BROKEN-RULES.md` sits at the top of the git repo. Its front matter holds the settings:

```
---
sources: **/AGENTS.md, **/CLAUDE.md, **/SKILL.md, .claude/**/*.md
timeout: 30
---
```

- `sources`: where `file` looks for the rule you quote (globs, relative to the register; `~` works).
- `timeout`: seconds per check.

Each break is one entry:

```
### B-004 Commit carried an AI co-author line — open
- **Rule:** "Never add AI co-author lines" (AGENTS.md:6)
- **Severity:** high · **Found:** 2026-10-16
- **Evidence:** the 'add report' commit ends with a Co-authored-by trailer
- **Fix:** a commit-msg hook that rejects the trailer
- **Check:** `! git log --format=%B | grep -qi '^co-authored-by:'`
- **Fix commit:** —
- **Last check:** 2026-10-16 fail
```

| Status | Meaning |
|---|---|
| `open` | filed; the check fails |
| `fixed` | a fix commit is recorded |
| `verified` | the check passes and the fix commit is in HEAD's history |
| `reopened` | a fixed or verified entry whose check fails again |
| `wontfix` | never checked; add a `- **Reason:**` line |

`update` changes only the status word and the `Last check:` line, so the rest of the file stays
yours to edit.

## Commands

`python3 scripts/broken_rules.py [--register PATH] <command>`

| Command | What it does |
|---|---|
| `init` | create `BROKEN-RULES.md` |
| `file --title --rule --severity --evidence --fix --check [--source]` | file a break. Refused unless the rule's words are in exactly one source file and the check fails now |
| `fixed B-NNN <commit>` | record the fix commit (must be in HEAD's history) |
| `run [--json PATH]` | re-check everything, print what moved, write nothing |
| `update` | the same, and write the new statuses |
| `check B-NNN` | run one check |
| `lint` | format problems, and rules whose quoted words are gone from their file |
| `next-id` | the next free id |
| `hook session-start [--text]` | what the session-start hook prints; `--text` gives only the text the agent sees |

`run` and `update` exit 1 when a fix reopened, a check could not run, or an entry is malformed.
A check that times out or exits 126 or 127 (not runnable, not found) is an error, never a pass.

## Writing a good check

Test the outcome, not the intent: the file, the commit or the setting the rule is about. Guard a
negation, since `! grep -q X file` also passes when the file is missing: write
`test -f file && ! grep -q X file`. Ready checks for common rules are in
[docs/recipes.md](docs/recipes.md).

## What it runs and what it reads

- It runs the check commands in your register, as shell commands, from the register's folder.
  They are code: review them like any script in your repo.
- It reads `BROKEN-RULES.md`, the source files in `sources`, and git history.
- The session-start hook reads `BROKEN-RULES.md` only. It runs no checks.
- It sends nothing over the network, collects nothing, and has no telemetry. Everything stays in
  your repo.

## Troubleshooting

- `no register`: run `init`, or pass `--register PATH`.
- `check passes now`: the check does not see the break. Rewrite it so it fails today.
- `could not run`: a typo or a missing tool in the check (exit 126 or 127).
- `rule found in more than one file`: add `--source <file>`.
- `not in HEAD's history`: the fix commit is on another branch or was rebased away. Record the
  commit that is on your branch.
- The hook shows nothing: it is silent when no break is open. Check that `python3` is on your PATH.

## Tests

```
python3 -m unittest discover -s tests
```

## Support

Questions and bugs: [GitHub issues](https://github.com/S3yon/broken-rules/issues).

## License

MIT
