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
