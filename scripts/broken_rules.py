#!/usr/bin/env python3
"""broken-rules: a register of the rules your coding agent broke.

Each entry in BROKEN-RULES.md quotes a rule from a file the agent loads (AGENTS.md, CLAUDE.md,
a SKILL.md), says what happened, and carries a shell check that fails while the break is real.
Every scan re-runs the checks:

  open      filed; the check fails
  fixed     a fix commit is recorded
  verified  the check passes and the fix commit is in HEAD's history
  reopened  a fixed or verified entry whose check fails again
  wontfix   never checked

A check that cannot run (timeout, exit 126 or 127) is ERROR and moves nothing. Python 3.9+,
standard library only. Run `broken_rules.py --help` for the commands.
"""
import argparse
import datetime
import glob
import json
import os
import re
import signal
import subprocess
import sys

SELF = os.path.abspath(__file__)
REGISTER_NAME = "BROKEN-RULES.md"
ENV_REGISTER = "BROKEN_RULES_FILE"
DEFAULT_SOURCES = ["**/AGENTS.md", "**/CLAUDE.md", "**/SKILL.md", ".claude/**/*.md"]
DEFAULT_TIMEOUT = 30
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__"}
STATUSES = ("open", "fixed", "verified", "reopened", "wontfix")
SEVERITIES = ("high", "med", "low")
DETAIL_MAX = 120
HOOK_MAX = 10

FENCE_OPEN = re.compile(r"^(`{3,})")
HEAD = re.compile(r"^### (B-\d{3,}) (.+) — (\S+)\s*$")
# One `**Key:** value` field, then the ` · ` before the next field on the same line, if any.
FIELD = re.compile(r"\*\*([^*]+):\*\*\s*(.*?)(?:\s+·\s+(?=\*\*[^*]+:\*\*)|$)")
RULE = re.compile(r'^"(.*)"\s+\((.+):(\d+)\)$')
HASH = re.compile(r"[0-9a-fA-F]{4,40}")
NOTHING = re.compile(r"[—–-]*")          # a field with no value yet


# ---- settings and register ------------------------------------------------

def parse_settings(text):
    """Settings from the register's front matter: `key: value` lines between `---` fences.
    Returns (settings, problems). A bad or unknown value is a problem and keeps the default."""
    settings = {"sources": list(DEFAULT_SOURCES), "timeout": DEFAULT_TIMEOUT}
    problems = []
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return settings, problems
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not sep:
            problems.append(f"front matter line is not 'key: value': {line.strip()!r}")
        elif key == "sources":
            sources = [s.strip() for s in value.split(",") if s.strip()]
            if sources:
                settings["sources"] = sources
            else:
                problems.append("sources is empty")
        elif key == "timeout":
            if value.isdigit() and int(value) > 0:
                settings["timeout"] = int(value)
            else:
                problems.append(f"timeout must be a whole number of seconds above 0, got {value!r}")
        else:
            problems.append(f"unknown setting {key!r}")
    return settings, problems


def _unticked(value):
    """`cmd` or `` cmd `` -> cmd. A value with no backticks comes back whole."""
    m = re.fullmatch(r"(`+)\s?(.*?)\s?\1", value)
    return m.group(2).strip() if m else value


def _entry(heading, line_no, fields):
    m = HEAD.match(heading)
    problems = []
    if m:
        bid, title, status = m.group(1), m.group(2).strip(), m.group(3)
        if status not in STATUSES:
            problems.append(f"unknown status {status!r}")
    else:
        parts = heading[4:].split()
        bid, title, status = (parts[0] if parts else ""), "", ""
        problems.append("malformed heading, want '### B-NNN <title> — <status>'")
    check = _unticked(fields.get("check", ""))
    check = None if NOTHING.fullmatch(check) else check
    if check is None and status != "wontfix":
        problems.append("empty Check line" if "check" in fields else "no Check line")
    fix = _unticked(fields.get("fix_commit", ""))
    rule, rule_ref = fields.get("rule", ""), None
    rm = RULE.match(rule)
    if rm:
        rule, rule_ref = rm.group(1), (rm.group(2).strip(), int(rm.group(3)))
    return {"id": bid, "title": title, "status": status, "severity": fields.get("severity", ""),
            "rule": rule, "rule_ref": rule_ref, "check": check,
            "fix_commit": None if NOTHING.fullmatch(fix) else fix.split()[0],
            "last_check": fields.get("last_check", ""), "reason": fields.get("reason", ""),
            "line_no": line_no, "problems": problems}


def parse_register(path):
    """One dict per `### B-NNN <title> — <status>` entry. A malformed entry is still returned,
    with `problems`, so one bad entry never hides the others. Lines inside a code fence are never
    entries, so a format example in the preface is not one."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    raw, cur, fence = [], None, None
    for n, line in enumerate(lines, 1):
        if fence is not None:
            if re.fullmatch(r"`{%d,}\s*" % len(fence), line):
                fence = None
        elif (m := FENCE_OPEN.match(line)):
            fence = m.group(1)
        elif line.startswith("### B-"):
            cur = (line, n, {})
            raw.append(cur)
        elif re.match(r"#{1,6} ", line):
            cur = None
        elif cur is not None and line.startswith("- "):
            pos = 2
            while (m := FIELD.match(line, pos)) and m.end() > pos:
                cur[2][m.group(1).strip().lower().replace(" ", "_")] = m.group(2).strip()
                pos = m.end()
    entries = [_entry(*r) for r in raw]
    ids = [e["id"] for e in entries]
    for e in entries:
        if ids.count(e["id"]) > 1:      # which twin to check or edit would be a guess
            e["problems"].append(f"duplicate id {e['id']}")
    return entries


def next_id(entries):
    nums = [int(m.group(1)) for e in entries if (m := re.match(r"B-(\d+)$", e["id"]))]
    return "B-%03d" % (max(nums, default=0) + 1)


# ---- checks ---------------------------------------------------------------

def _short(text):
    text = " ".join(text.split())
    return text if len(text) <= DETAIL_MAX else text[:DETAIL_MAX - 3] + "..."


def run_check(cmd, root, timeout):
    """Run one check in a shell, cwd root, stdin at EOF. Returns (pass|fail|error, detail).
    Only exit 0 is a pass. A timeout, a command that cannot start, or exit 126/127 (not
    runnable, not found) is error: a check that cannot run proves nothing either way."""
    if not cmd or not cmd.strip():
        return "error", "empty check"
    try:
        p = subprocess.Popen(cmd, shell=True, cwd=root, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, errors="replace", start_new_session=True)
    except OSError as e:
        return "error", f"cannot run {_short(cmd)}: {e}"
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:                     # the whole group, so a pipeline's children die too
            os.killpg(p.pid, signal.SIGKILL)
        except (OSError, AttributeError):
            p.kill()
        p.communicate()
        return "error", f"timeout after {timeout}s: {_short(cmd)}"
    if p.returncode == 0:
        return "pass", "exit 0"
    last = next((l for l in reversed(out.splitlines()) if l.strip()), "")
    tail = f" ({_short(last)})" if last else ""
    if p.returncode in (126, 127):
        return "error", f"exit {p.returncode}, command not found or not runnable: {_short(cmd)}{tail}"
    return "fail", f"exit {p.returncode}: {_short(cmd)}{tail}"


def next_status(status, passed, fix_ok):
    """The status a check result moves an entry to. fix_ok: True when the fix commit is in
    HEAD's history, False when not, None when none is recorded. Only a fixed or reopened entry
    whose check passes and whose fix commit resolves is verified; a fixed or verified entry whose
    check fails is reopened. Everything else, and wontfix always, keeps its status."""
    if status in ("fixed", "verified") and not passed:
        return "reopened"
    if status in ("fixed", "reopened") and passed and fix_ok:
        return "verified"
    return status


def fix_in_history(commit, root):
    """True when the commit is an ancestor of HEAD, False when not (a typo, another branch, a
    rebased-away commit, no git repo), None when no commit is recorded."""
    if commit is None:
        return None
    if not HASH.fullmatch(commit):     # also keeps a value like --help away from git
        return False
    try:
        r = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor",
                            f"{commit}^{{commit}}", "HEAD"],
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=DEFAULT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def check_entry(entry, root, timeout):
    """Run one entry's check. Returns (result, detail, new_status); result is pass, fail or error.
    A check that cannot run, and a pass on a fixed or reopened entry whose fix commit is missing
    or not in HEAD's history, are error and move nothing."""
    status = entry["status"]
    result, detail = run_check(entry["check"], root, timeout)
    if result == "error":
        return "error", detail, status
    passed = result == "pass"
    fix_ok = None
    if passed and status in ("fixed", "reopened"):
        fix_ok = fix_in_history(entry["fix_commit"], root)
        if not fix_ok:
            why = ("no fix commit recorded" if fix_ok is None
                   else f"fix commit {entry['fix_commit']} is not in HEAD's history")
            return "error", why, status
    return result, detail, next_status(status, passed, fix_ok)


def check_all(entries, root, timeout):
    """Re-check every entry except wontfix. Returns (results, lines, attention): results maps an
    id to (new_status, result); lines are what to print; attention is True when a person should
    look (an error, a malformed entry, a reopen). An open entry that still fails prints nothing."""
    results, lines, attention = {}, [], False
    for e in entries:
        bid, status = e["id"], e["status"]
        if e["problems"]:
            lines.append(f"ERROR {bid} " + "; ".join(e["problems"]))
            attention = True
        elif status != "wontfix":
            result, detail, new = check_entry(e, root, timeout)
            results[bid] = (new, result)
            if new != status:
                lines.append(f"{new.upper()} {bid} {detail}")
                attention = attention or new == "reopened"
            elif result == "error":
                lines.append(f"ERROR {bid} {detail}")
                attention = True
            elif result == "pass" and status == "open":
                lines.append(f"NOTE {bid} open but check passes; record the fix commit")
    return results, lines, attention


def summary(entries, results):
    """`open N · fixed N · verified N · reopened N · wontfix N` after the moves in results."""
    counts = dict.fromkeys(STATUSES, 0)
    for e in entries:
        status = results.get(e["id"], (e["status"],))[0]
        if status in counts:
            counts[status] += 1
    return " · ".join(f"{s} {counts[s]}" for s in STATUSES)


# ---- writing the register -------------------------------------------------

def _read_raw(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _write_raw(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _newline(text):
    return "\r\n" if "\r\n" in text else "\n"


def edit_entries(path, edits):
    """Edit entries in place. edits maps an id to (status or None, {field label: value}). The
    status word at the end of the heading and each named `- **Label:**` line are replaced; a
    field line the entry lacks is added after its last line. Every other byte stays as it was,
    and nothing inside a code fence is touched."""
    text = _read_raw(path)
    nl = _newline(text)
    out, fence, target, seen = [], None, None, set()

    def close_entry():
        if target is None:
            return
        missing = [k for k in target[1] if k not in seen]
        if not missing:
            return
        i = len(out) - 1
        while i >= 0 and not out[i].strip():
            i -= 1
        if i >= 0 and not out[i].endswith("\n"):
            out[i] += nl
        for k in reversed(missing):
            out.insert(i + 1, f"- **{k}:** {target[1][k]}{nl}")

    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        end = line[len(body):]
        if fence is not None:
            if re.fullmatch(r"`{%d,}\s*" % len(fence), body):
                fence = None
        elif (m := FENCE_OPEN.match(body)):
            fence = m.group(1)
        elif re.match(r"#{1,6} ", body):
            close_entry()
            target, seen = None, set()
            m = HEAD.match(body)
            if m and m.group(1) in edits:
                target = edits[m.group(1)]
                if target[0]:
                    line = body[:m.start(3)] + target[0] + end
        elif target is not None:
            for label, value in target[1].items():
                if body.startswith(f"- **{label}:**"):
                    seen.add(label)
                    line = f"- **{label}:** {value}{end}"
        out.append(line)
    close_entry()
    new = "".join(out)
    if new != text:
        _write_raw(path, new)


def update_register(path, results, today):
    """Write check results: results maps an id to (new_status, result)."""
    edit_entries(path, {bid: (status, {"Last check": f"{today} {result}"})
                        for bid, (status, result) in results.items()})


def set_fixed(path, bid, commit):
    """Record a fix commit and move the entry to fixed."""
    edit_entries(path, {bid: ("fixed", {"Fix commit": commit})})


def _one_line(text):
    return " ".join(str(text).split())


def format_entry(bid, title, rule, ref, severity, found, evidence, fix, check):
    """A new open entry. ref is (path, line). A check holding a backtick gets double ticks."""
    check = _one_line(check)
    ticked = f"`` {check} ``" if "`" in check else f"`{check}`"
    return (f"### {bid} {_one_line(title)} — open\n"
            f"- **Rule:** \"{_one_line(rule)}\" ({ref[0]}:{ref[1]})\n"
            f"- **Severity:** {severity} · **Found:** {found}\n"
            f"- **Evidence:** {_one_line(evidence)}\n"
            f"- **Fix:** {_one_line(fix)}\n"
            f"- **Check:** {ticked}\n"
            f"- **Fix commit:** —\n"
            f"- **Last check:** {found} fail\n")


def append_entry(path, entry_text):
    """Append an entry after exactly one blank line, in the file's own line endings."""
    text = _read_raw(path)
    nl = _newline(text)
    body = re.sub(r"(?:\r?\n[ \t]*)+\Z", "", text)     # blank lines only, never a line's own spaces
    lead = body + nl + nl if body else ""
    _write_raw(path, lead + entry_text.replace("\n", nl))


# ---- rule lookup and filing -----------------------------------------------

class RuleError(Exception):
    """The rule quote cannot be tied to exactly one source file."""


class FileError(Exception):
    """A break cannot be filed as given."""


def _normalized(text):
    """text with `*` and backticks dropped and whitespace runs collapsed to one space, plus the
    1-based source line of every character kept."""
    chars, lines, line, space = [], [], 1, True
    for ch in text:
        if ch.isspace():
            if not space:
                chars.append(" ")
                lines.append(line)
                space = True
        elif ch not in "*`":
            chars.append(ch)
            lines.append(line)
            space = False
        if ch == "\n":
            line += 1
    return "".join(chars).rstrip(), lines


def display_path(path, root):
    """path relative to root when inside it, else with the home folder shown as ~."""
    path = os.path.abspath(path)
    rel = os.path.relpath(path, root)
    if not rel.startswith(os.pardir):
        return rel
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home + os.sep) else path


def resolve_path(path, root):
    path = os.path.expanduser(path)
    return path if os.path.isabs(path) else os.path.join(root, path)


def source_files(root, sources, exclude=()):
    """Files the source globs match, in glob order, deduplicated, skipping SKIP_DIRS and exclude."""
    seen, out = {os.path.realpath(p) for p in exclude}, []
    for pattern in sources:
        for p in sorted(glob.glob(resolve_path(pattern, root), recursive=True)):
            parts = os.path.relpath(p, root).split(os.sep)
            real = os.path.realpath(p)
            if os.path.isfile(p) and not SKIP_DIRS.intersection(parts) and real not in seen:
                seen.add(real)
                out.append(p)
    return out


def find_rule(quote, root, sources, source=None, exclude=()):
    """(path, line) of the one source file holding the quote. Matching ignores whitespace runs,
    `*` and backticks; it is literal and case-sensitive. Raises RuleError when no file or more
    than one file holds it."""
    want, _ = _normalized(quote)
    if not want:
        raise RuleError("the rule quote is empty")
    if source:
        files = [resolve_path(source, root)]
        if not os.path.isfile(files[0]):
            raise RuleError(f"source file not found: {source}")
    else:
        files = source_files(root, sources, exclude)
        if not files:
            raise RuleError("no source files match " + ", ".join(sources))
    hits = []
    for path in files:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text, lines = _normalized(f.read())
        except OSError:
            continue
        i = text.find(want)
        if i >= 0:
            hits.append((display_path(path, root), lines[i]))
    if not hits:
        names = [display_path(p, root) for p in files]
        more = f" and {len(names) - 5} more" if len(names) > 5 else ""
        raise RuleError(f"rule not found in {', '.join(names[:5])}{more}; quote its exact words")
    if len(hits) > 1:
        raise RuleError("rule found in more than one file, pass --source: "
                        + ", ".join(f"{p}:{n}" for p, n in hits))
    return hits[0]


def file_break(register, root, settings, title, rule, severity, evidence, fix, check,
               source=None, today=None):
    """Append a new open entry. Returns (id, (path, line)). Refuses when the register is missing,
    a field is empty, the rule is not in exactly one source, or the check does not fail now."""
    if severity not in SEVERITIES:
        raise FileError(f"severity must be high, med or low, got {severity!r}")
    for name, value in (("title", title), ("rule", rule), ("evidence", evidence), ("fix", fix),
                        ("check", check)):
        if not str(value or "").strip():
            raise FileError(f"{name} is empty")
    if "\n" in check.strip():
        raise FileError("check must be one line")
    if not os.path.isfile(register):
        raise FileError(f"no register at {register}; run init first")
    entries = parse_register(register)
    try:
        ref = find_rule(rule, root, settings["sources"], source, exclude=[register])
    except RuleError as e:
        raise FileError(str(e))
    result, detail = run_check(check.strip(), root, settings["timeout"])
    if result == "pass":
        raise FileError("check passes now, so it cannot show the break; "
                        "write one that fails while the rule is broken")
    if result == "error":
        raise FileError(f"check could not run: {detail}")
    bid = next_id(entries)
    today = today or datetime.date.today().isoformat()
    append_entry(register, format_entry(bid, title, rule, ref, severity, today, evidence, fix,
                                        check.strip()))
    return bid, ref
