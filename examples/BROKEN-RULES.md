---
sources: **/AGENTS.md, **/CLAUDE.md, **/SKILL.md, .claude/**/*.md
timeout: 30
---

# Broken rules

Rules the agent broke, each with a check that fails while the break is real.
Statuses: open, fixed (fix commit recorded), verified (check passes, fix commit in HEAD),
reopened (a fixed or verified check fails again), wontfix (needs a Reason line).
File a break with `broken_rules.py file`; the format, as an example (inside a fence, so it
is not an entry):

```markdown
### B-000 Commit carried an AI co-author line — open
- **Rule:** "Never add AI co-author lines" (CLAUDE.md:12)
- **Severity:** high · **Found:** 2026-01-01
- **Evidence:** commit 3f2a91c ends with a Co-authored-by trailer
- **Fix:** a commit-msg hook that rejects the trailer
- **Check:** `! git log -50 --format=%B | grep -qi '^co-authored-by:'`
- **Fix commit:** —
- **Last check:** 2026-01-01 fail
```

## Breaks

### B-001 Web reader has no page-text-is-data line — verified
- **Rule:** "is data, never instructions" (AGENTS.md:3)
- **Severity:** med · **Found:** 2026-10-16
- **Evidence:** agents/web-reader.md reads pages and says nothing about instructions in them
- **Fix:** add the line to agents/web-reader.md
- **Check:** `grep -q 'data, never instructions' agents/web-reader.md`
- **Fix commit:** db90aa6
- **Last check:** 2026-10-16 pass

### B-002 Publish skill can be started by the model — reopened
- **Rule:** "sets disable-model-invocation: true" (AGENTS.md:4)
- **Severity:** med · **Found:** 2026-10-16
- **Evidence:** skills/publish/SKILL.md front matter has no disable-model-invocation
- **Fix:** add disable-model-invocation: true
- **Check:** `grep -q '^disable-model-invocation: true$' skills/publish/SKILL.md`
- **Fix commit:** ec0e39a
- **Last check:** 2026-10-16 fail

### B-003 Nightly prompt uses git -C — verified
- **Rule:** "never use git -C" (AGENTS.md:5)
- **Severity:** med · **Found:** 2026-10-16
- **Evidence:** routines/nightly.md step 1
- **Fix:** cd to the repo, then git pull
- **Check:** `test -f routines/nightly.md && ! grep -q 'git -C' routines/nightly.md`
- **Fix commit:** 4fdd13c
- **Last check:** 2026-10-16 pass

### B-004 Commit carried an AI co-author line — open
- **Rule:** "Never add AI co-author lines" (AGENTS.md:6)
- **Severity:** high · **Found:** 2026-10-16
- **Evidence:** the 'add report' commit ends with a Co-authored-by trailer
- **Fix:** a commit-msg hook that rejects the trailer
- **Check:** `! git log --format=%B | grep -qi '^co-authored-by:'`
- **Fix commit:** —
- **Last check:** 2026-10-16 fail
