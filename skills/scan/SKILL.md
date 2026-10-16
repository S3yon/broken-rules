---
name: scan
description: Re-check every entry in the project's BROKEN-RULES.md register and report which broken rules are now verified fixed, still open, or reopened. Use when the user asks to scan, check or update the broken-rules register, asks whether rules the agent broke before are fixed now, or before a release.
---

# Scan the register

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/broken_rules.py" update`. It re-runs every check
   except wontfix, writes the new statuses, and prints one line per change plus a summary.
   "no register" means there is nothing to scan: say so and stop.
2. Report the summary line first, then one line per printed entry:
   - `VERIFIED`: the fix held. Nothing to do.
   - `REOPENED`: a fix stopped holding. Run
     `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/broken_rules.py" check B-NNN`, read the output, and
     find the change that undid it (`git log` on the files the check reads). Offer to fix it.
   - `ERROR … no fix commit recorded` or `not in HEAD's history`: the check passes but the fix
     commit is missing or on another branch. Find the commit that fixed it and record it with
     `fixed B-NNN <commit>`.
   - `ERROR` from a check that could not run: the check itself is broken. Show the command.
   - `NOTE … open but check passes`: it looks fixed. Find the fix commit and record it.
3. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/broken_rules.py" lint` and report any line it
   prints, for example a rule whose quoted words are no longer in its file.

## Done when
`update` ran and wrote the register, and the user has the summary plus one line for each entry
that moved, errored or needs a fix commit.
