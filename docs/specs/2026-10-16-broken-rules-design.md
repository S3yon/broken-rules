# broken-rules: design

Date: 2026-10-16. Status: approved (name, scope, config and contents picked from four options each).

## What it is
A register of the rules your coding agent broke. Each entry quotes the rule from the file the
agent loads (AGENTS.md, CLAUDE.md, a SKILL.md), says what happened, and carries a shell check
that fails while the break is real. The register is re-checked on every scan:

- `open`: filed; the check fails.
- `fixed`: a fix commit is recorded.
- `verified`: the check passes and the fix commit is in HEAD's history.
- `reopened`: a fixed or verified entry whose check fails again.
- `wontfix`: never checked; needs a `Reason:` line.

It is not a config linter (those read the instruction files) and not a transcript checker (that
reads one session). It keeps a running record across sessions and proves a fix held.

## Success criteria
- `broken-rules file` refuses a check that passes now, errors, times out, or cannot run
  (exit 126/127): a filed break always has a check that sees it.
- `file` refuses a rule quote that is not in the cited file; `lint` flags a quote that has since
  been edited out (the rule changed, so the entry needs a look).
- `update` moves fixed → verified only when the check passes and the fix commit is an ancestor of
  HEAD; fixed/verified → reopened when the check fails. It changes only the status word and the
  `Last check:` line, byte for byte.
- A check that cannot run is ERROR and moves nothing. Nothing that fails to run reads as a pass.
- The session-start hook lists open and reopened breaks to the agent and is silent in a repo with
  no register. It never runs checks.
- Python 3.9+ standard library only. `python3 -m unittest discover -s tests` passes.
- `claude plugin validate .` passes. No personal names or paths in the repo.

## Out of scope for v1
Health probes per system, upstream release watch, a judgement agent, a CI action. The format
leaves room for them.

## Layout
```
.claude-plugin/plugin.json, marketplace.json
scripts/broken_rules.py      the CLI and engine, one file, stdlib
skills/file-break/SKILL.md   turn a broken rule into an entry with a failing check
skills/scan/SKILL.md         re-check the register and report what moved
hooks/hooks.json             SessionStart → broken_rules.py hook session-start
docs/recipes.md              ready check commands for common rules
examples/demo.sh             builds a throwaway repo and runs the whole loop
examples/BROKEN-RULES.md     the register the demo produces
tests/                       unittest suite
```

## The register: `BROKEN-RULES.md`
Found by `--register PATH`, else `$BROKEN_RULES_FILE`, else `BROKEN-RULES.md` in the git top
level of the working directory (the working directory itself outside git). Checks run with the
register's folder as the working directory.

Front matter holds the settings, `key: value` lines between `---` fences, no YAML library:

```
---
sources: AGENTS.md, CLAUDE.md, .claude/CLAUDE.md, **/SKILL.md
timeout: 30
---
```

- `sources`: comma-separated globs, relative to the register's folder; where `file` looks for a
  rule quote when no `--source` is given. Default as above.
- `timeout`: seconds per check, default 30.
- An unknown key is a lint problem.

Entry format. Anything inside a code fence is never an entry, so the preface can show an example.

```
### B-004 Commit carried an AI co-author line — open
- **Rule:** "Never add AI co-author lines" (CLAUDE.md:12)
- **Severity:** high · **Found:** 2026-10-16
- **Evidence:** commit 3f2a91c ends with a Co-authored-by trailer
- **Fix:** a commit-msg hook that rejects the trailer
- **Check:** `! git log -50 --format=%B | grep -qi '^co-authored-by:'`
- **Fix commit:** —
- **Last check:** 2026-10-16 fail
```

Severity: `high` (wrong output, data loss, a secret or a public action), `med` (a missing guard,
repeated friction), `low` (style). Ids are `B-NNN`, never reused.

## CLI
`python3 scripts/broken_rules.py [--register PATH] <command>`

| Command | Does | Writes |
|---|---|---|
| `init` | create the register with front matter and a fenced example | register |
| `file --title --rule --severity --evidence --fix --check [--source FILE]` | locate the quote, run the check (must fail), append the entry with the next id | register |
| `fixed B-NNN <commit>` | record the fix commit; open/reopened → fixed. Refuses a commit not in HEAD's history | register |
| `run [--json PATH]` | re-check all but wontfix; print moves; exit 1 on an error, a malformed entry or a reopen | nothing |
| `update` | as `run`, then write statuses and `Last check:` lines | register |
| `check B-NNN` | run one check | nothing |
| `lint` | malformed entries, unknown status or key, duplicate ids, bad severity, missing Rule or Check, rule quote gone from its file | nothing |
| `next-id` | print the next free id | nothing |
| `hook session-start` | SessionStart JSON listing open and reopened breaks (max 10, then "and N more") | nothing |

Output lines: `VERIFIED B-002 …`, `REOPENED B-003 …`, `ERROR B-004 …`, `NOTE B-001 open but check
passes; record the fix commit`, then one summary line with counts per status.

Rule lookup: the quote is matched per line after collapsing whitespace, case-sensitive. With
`--source`, only that file; else every file the `sources` globs match. No hit: refuse. Hits in
more than one file: refuse and list them, so the caller passes `--source`. The entry records the
first hit's `path:line`.

## Skills
- `file-break`: when the user corrects the agent for breaking a written rule, or the agent notices
  it broke one. Find the rule's exact words, gather evidence (commit, file:line, output), write a
  check that tests the outcome (a file, a commit, a config), never the agent's intent, then run
  `file`. If the CLI refuses the check, fix the check, never the rule. Then offer the fix.
- `scan`: run `update`, report moves and the summary, explain each reopened break.
Both call the script through the plugin root path.

## Hook
SessionStart, matcher `startup|resume|clear|compact`. Prints the additionalContext JSON only when a
register exists and has open or reopened breaks; otherwise prints nothing and exits 0. A register
that cannot be parsed prints one line saying so; the hook never blocks a session.

## Out of the box
- `docs/recipes.md`: checks for common rules (co-author trailer, subject length, conventional
  subject, a secret pattern in tracked files, main history not rewritten, a required front-matter
  line, a banned command in a file, a file kept fresh).
- `examples/demo.sh`: a temp git repo with an AGENTS.md and three files that break its rules
  (rewritten from a real register: page text treated as instructions, a publish skill the model
  can start on its own, a banned `git -C` in a scheduled prompt, a co-author trailer). It files
  the breaks, commits fixes, records them, updates (VERIFIED), undoes one fix, and runs again
  (REOPENED). The README shows its real output.

## Testing
unittest, test-first: parser, front matter, rule lookup, check results (pass, fail, 126/127,
timeout, stdin at EOF), status moves (the full table), fix commit ancestry (side branch, typo,
non-hash), byte-preserving update, fenced example ignored, `file` refusals, `fixed`, lint, hook
output, and the demo end to end.
