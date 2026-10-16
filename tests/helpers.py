import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPT = os.path.join(REPO, "scripts", "broken_rules.py")
sys.path.insert(0, os.path.join(REPO, "scripts"))

import broken_rules as br  # noqa: E402

HEAD = """---
sources: AGENTS.md
timeout: 30
---

# Broken rules

Format, as an example. It is inside a fence, so it is not an entry:

```markdown
### B-099 Example in a fence — open
- **Rule:** "Example" (AGENTS.md:1)
- **Check:** `false`
- **Last check:** 2026-01-01 fail
```

## Breaks

"""


class TempCase(unittest.TestCase):
    """A test with a temp folder at self.tmp, removed afterwards."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def write(self, rel, text="", base=None, newline=None):
        path = os.path.join(base or self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)
        return path

    def raw(self, path):
        with open(path, "rb") as f:
            return f.read()

    def git(self, *args, base=None):
        r = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
             "-c", "core.hooksPath=/dev/null", "-c", "init.defaultBranch=main",
             "-C", base or self.tmp, *args],
            capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def repo(self, base=None):
        """A git repo with one empty commit. Returns its full hash."""
        base = base or self.tmp
        self.git("init", "-q", base=base)
        self.git("commit", "-q", "--allow-empty", "-m", "init", base=base)
        return self.git("rev-parse", "HEAD", base=base)

    def cli(self, *args, cwd=None, env=None):
        full = {k: v for k, v in os.environ.items()
                if k not in ("BROKEN_RULES_FILE", "CLAUDE_PROJECT_DIR")}
        full.update(env or {})
        r = subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd or self.tmp,
                           capture_output=True, text=True, timeout=60, env=full,
                           stdin=subprocess.DEVNULL)
        return r.returncode, r.stdout + r.stderr


def entry(bid, title, status, check="true", fix="—", sev="low", rule='"Example" (AGENTS.md:1)',
          last="2026-09-01 fail", extra=""):
    return (f"### {bid} {title} — {status}\n"
            f"- **Rule:** {rule}\n"
            f"- **Severity:** {sev} · **Found:** 2026-09-01\n"
            f"{extra}"
            f"- **Check:** `{check}`\n"
            f"- **Fix commit:** {fix}\n"
            f"- **Last check:** {last}\n\n")
