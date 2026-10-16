---
name: file-break
description: File a broken rule in the project's BROKEN-RULES.md register, with a shell check that fails while the break is real. Use when the user corrects you for breaking a rule written in AGENTS.md, CLAUDE.md, a skill or another instruction file ("you were told not to", "that breaks the rule in AGENTS.md", "log this as a broken rule"), or when you notice you broke one yourself.
---

# File a broken rule

Every command below is the plugin's script; type it in full:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/broken_rules.py"`.

1. Check for a register: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/broken_rules.py" next-id`.
   If it says "no register", run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/broken_rules.py" init`
   and tell the user it created BROKEN-RULES.md at the repo root.
2. Find the rule in the file that holds it. Quote a phrase only that rule contains, word for word.
   Markdown `*` and backticks may be left out; wrapped lines are fine.
3. Gather evidence you can show: a commit hash, a file and line, a command's output.
4. Write the check: one shell command that exits non-zero while the break is real and 0 once it
   is fixed. Test the outcome (a file, a commit, a setting), never your own intent. Guard a
   negation: `test -f F && ! grep -q X F`. Ready-made checks:
   `${CLAUDE_PLUGIN_ROOT}/docs/recipes.md`.
5. File it:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/broken_rules.py" file --title "<what went wrong>" \
     --rule "<exact words>" --severity <high|med|low> --evidence "<what you saw>" \
     --fix "<what would fix it>" --check '<command>'
   ```

   - `check passes now`: the check does not see the break. Rewrite the check. Never edit the
     rule to make a check fail.
   - `could not run`: a typo or a missing tool in the check. Fix the command.
   - `found in more than one file`: add `--source <file>`.
   - `rule not found`: quote the rule's exact words from the file.
6. Tell the user the new id, the rule and the check in two lines, then offer to fix it. Once the
   fix is committed: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/broken_rules.py" fixed B-NNN <commit>`,
   then `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/broken_rules.py" update` to verify it.

Severity: `high` for wrong output, lost data, an exposed secret or an unapproved public action;
`med` for a missing guard or repeated friction; `low` for style.

## Done when
The script printed `FILED B-NNN`, and the user knows the id, the check, and how the fix gets verified.
