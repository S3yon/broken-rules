# broken-rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A plugin that keeps a register of the rules a coding agent broke, each with a check that fails while the break is real.

**Architecture:** One stdlib Python file (`scripts/broken_rules.py`) holds the parser, check runner, status moves, writer and CLI. Two skills and a SessionStart hook call it through the plugin root. A demo script drives the full loop in a throwaway git repo.

**Tech Stack:** Python 3.9+ standard library, unittest, git, a plugin manifest.

**Spec:** `docs/specs/2026-10-16-broken-rules-design.md`

## Global Constraints
- Python 3.9+ standard library only; no third-party imports.
- Statuses exactly `open fixed verified reopened wontfix`; severities `high med low`; ids `B-NNN`.
- Heading `### B-NNN <title> — <status>` (em dash with spaces); fields `- **Key:** value`, several per line joined by ` · `.
- Register default name `BROKEN-RULES.md`; env override `BROKEN_RULES_FILE`; default timeout 30 s.
- Default sources: `AGENTS.md, CLAUDE.md, .claude/CLAUDE.md, **/SKILL.md`.
- Exit 126/127, timeout, or OSError from a check is `error`, never `fail` or `pass`.
- No personal names or local paths anywhere in the repo; no AI credit lines in commits.

## Review Focus
- A register with Windows line endings: update must keep `\r\n` (test in Task 3).
- A check that reads stdin must see EOF at once, not hang (test in Task 2).
- A rule quote containing regex characters (`*`, `(`) must match literally (test in Task 4).
- Running from a subfolder of the repo must find the register at the git top level (test in Task 5).
- A hook run in a repo with no register, or a malformed one, must exit 0 and never block (test in Task 6).

---

### Task 1: Register parser and front matter

**Files:** Create `scripts/broken_rules.py`, `tests/test_parse.py`, `tests/helpers.py`

**Interfaces — Produces:**
- `parse_settings(text: str) -> tuple[dict, list[str]]` → `({"sources": [...], "timeout": 30}, problems)`
- `parse_register(path: str) -> list[dict]`: keys `id, title, status, severity, rule, rule_ref, check, fix_commit, last_check, line_no, problems`
- `next_id(entries) -> str`

- [ ] Tests: two entries parse with all fields; a `### B-099` inside a ```` ```markdown ```` fence is not an entry; `Check:` backticks stripped; `Fix commit: —` → None; missing Check → problem `no Check line` (not for wontfix); unknown status → problem; duplicate id → problem on both; title keeps an inner ` — `; `Rule:` `"quote" (AGENTS.md:3)` → `rule="quote"`, `rule_ref=("AGENTS.md", 3)`; settings defaults, custom sources split on commas, bad timeout and unknown key → problems; next_id max+1 with gaps, `B-001` on empty.
- [ ] Run `python3 -m unittest discover -s tests` → fails (no module).
- [ ] Implement, port the fence-aware parser from the leak scanner design.
- [ ] Tests pass. Commit `feat(register): parse entries and front matter settings`.

### Task 2: Checks and status moves

**Files:** Modify `scripts/broken_rules.py`; create `tests/test_checks.py`

**Interfaces — Produces:**
- `run_check(cmd: str, root: str, timeout: int) -> tuple[str, str]` → `("pass"|"fail"|"error", detail)`
- `next_status(status, passed: bool, fix_ok: bool|None) -> str`
- `fix_in_history(commit: str|None, root: str) -> bool|None`
- `check_entry(entry, root, timeout) -> tuple[result, detail, new_status]`
- `check_all(entries, root, timeout) -> tuple[dict id->(new_status, result), list[str] lines, bool attention]`

- [ ] Tests: `true` pass, `false` fail, `nosuchcmd-xyz` error (127), empty error, `sleep 5` with timeout 1 → error in under 3 s, `read x` → fail at EOF; cwd is root; full move table (16 rows, as the leak scanner's); fix commit: full and short hash resolve, side-branch commit and `deadbee` and `--help` → False, None → None, outside git → False; fixed+pass+no commit → error, status kept; wontfix never run (a `touch ran` check leaves no file); open+pass → `NOTE … record the fix commit`.
- [ ] Run → fail. Implement. Run → pass. Commit `feat(check): run checks and move statuses`.

### Task 3: Writing the register

**Files:** Modify `scripts/broken_rules.py`; create `tests/test_write.py`

**Interfaces — Produces:**
- `update_register(path, results: dict, today: str) -> None` (only status word + `Last check:`; adds the line when missing)
- `append_entry(path, entry_text: str) -> None`
- `format_entry(id, title, rule, ref, severity, found, evidence, fix, check) -> str`
- `set_fixed(path, id, commit) -> None`

- [ ] Tests: byte-for-byte update on a fixture with trailing spaces and non-ASCII; fenced example untouched; missing `Last check:` added after the entry's last line; file with no final newline; CRLF file keeps CRLF; `append_entry` adds one blank line before the entry; `set_fixed` changes status to fixed and the `Fix commit:` value only.
- [ ] Run → fail. Implement. Run → pass. Commit `feat(register): update statuses and append entries in place`.

### Task 4: Rule lookup and `file`

**Files:** Modify `scripts/broken_rules.py`; create `tests/test_file.py`

**Interfaces — Produces:**
- `find_rule(quote, root, sources: list[str], source: str|None) -> tuple[path, line]` raising `RuleError(msg)`
- `file_break(register, root, settings, **fields) -> str` (the new id) raising `FileError(msg)`

- [ ] Tests: quote found with collapsed whitespace; `Never use (rm -rf *)` matched literally; not found → error naming the files searched; two files → error listing both; `--source` limits the search; check that passes → refused `check passes now`; check exit 127 → refused; timeout → refused; good input appends `B-001` with `Last check: <today> fail` and `Fix commit: —`; severity outside high/med/low refused.
- [ ] Run → fail. Implement. Run → pass. Commit `feat(file): file a break only with a quote that exists and a check that fails`.

### Task 5: CLI

**Files:** Modify `scripts/broken_rules.py`; create `tests/test_cli.py`

**Interfaces — Consumes:** Tasks 1-4. **Produces:** `main(argv) -> int`; commands `init file fixed run update check lint next-id hook`.

- [ ] Tests (subprocess, `BROKEN_RULES_FILE` stripped from env): `init` creates a register that lints clean, second `init` refuses; `run` prints `VERIFIED`/`REOPENED`/`ERROR`/`NOTE` lines and a summary `open N · fixed N · verified N · reopened N · wontfix N`, never writes; `update` writes, a second update repeats no move; `check B-404` → exit 1; `fixed B-001 <sha>` → status fixed, refuses a side-branch sha; `lint` reports a rule quote no longer in its file; register found from a subfolder via git top level; `--register` and env override; missing register → `ERROR … no register` exit 1; `run --json` written on every path.
- [ ] Run → fail. Implement. Run → pass. Commit `feat(cli): commands for init, file, fixed, run, update, check, lint`.

### Task 6: Session hook

**Files:** Modify `scripts/broken_rules.py`; create `hooks/hooks.json`, `tests/test_hook.py`

- [ ] Tests: no register → no output, exit 0; register with only verified → no output; 12 open/reopened → JSON with `hookSpecificOutput.hookEventName == "SessionStart"`, 10 entries listed by id, title and rule, then `and 2 more`; unreadable register → one line, exit 0; uses `CLAUDE_PROJECT_DIR` when set.
- [ ] Run → fail. Implement `hook_session_start(root) -> str`. Run → pass. Commit `feat(hook): show open and reopened breaks at session start`.

### Task 7: Plugin, skills, recipes, demo, README

**Files:** Create `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `skills/file-break/SKILL.md`, `skills/scan/SKILL.md`, `docs/recipes.md`, `examples/demo.sh`, `examples/BROKEN-RULES.md`, `tests/test_demo.py`, `README.md`, `LICENSE`, `CHANGELOG.md`, `.github/workflows/test.yml`, `.gitignore`

- [ ] Test: `tests/test_demo.py` runs `examples/demo.sh` and expects `VERIFIED B-001`, `REOPENED`, exit codes as documented, and every recipe in `docs/recipes.md` marked `<!-- run -->` runs in a fixture repo without `error`.
- [ ] Write demo, recipes, skills, manifests. Tests pass. `claude plugin validate .` passes.
- [ ] README: what it does (one paragraph), install, a demo block pasted from a real `examples/demo.sh` run, the entry format, commands, how it differs from config linters, test command. Commit per file group.
