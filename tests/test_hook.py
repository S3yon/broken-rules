import json
import os

from helpers import HEAD, REPO, TempCase, entry


class HookTest(TempCase):
    def hook(self, env=None, cwd=None):
        return self.cli("hook", "session-start", env=env, cwd=cwd)

    def test_silent_without_a_register(self):
        self.assertEqual(self.hook(), (0, ""))

    def test_silent_when_nothing_is_open(self):
        self.write("BROKEN-RULES.md", HEAD + entry("B-001", "A", "verified") + entry("B-002", "B", "fixed"))
        self.assertEqual(self.hook(), (0, ""))

    def test_lists_reopened_first_then_open_capped_at_ten(self):
        body = "".join(entry(f"B-{i:03d}", f"Title {i}", "open", rule=f'"Rule {i}" (AGENTS.md:{i})')
                       for i in range(1, 12))
        body += entry("B-012", "Came back", "reopened", rule='"Rule 12" (AGENTS.md:12)')
        body += entry("B-013", "Done", "verified")
        self.write("BROKEN-RULES.md", HEAD + body)
        code, out = self.hook()
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["hookSpecificOutput"]["hookEventName"], "SessionStart")
        text = data["hookSpecificOutput"]["additionalContext"]
        lines = [l for l in text.splitlines() if l.startswith("- B-")]
        self.assertEqual(len(lines), 10)
        self.assertTrue(lines[0].startswith("- B-012 (reopened) Came back"))
        self.assertIn('Rule: "Rule 12" (AGENTS.md:12)', lines[0])
        self.assertIn("and 2 more", text)
        self.assertNotIn("B-013", text)
        self.assertLess(len(text), 10000)

    def test_uses_project_dir(self):
        proj = os.path.join(self.tmp, "proj")
        self.write("BROKEN-RULES.md", HEAD + entry("B-001", "Elsewhere", "open"), base=proj)
        code, out = self.hook(env={"CLAUDE_PROJECT_DIR": proj}, cwd=REPO)
        self.assertEqual(code, 0)
        self.assertIn("B-001", out)

    def test_unreadable_register_never_blocks(self):
        os.makedirs(os.path.join(self.tmp, "BROKEN-RULES.md"))      # a folder where the file should be
        code, out = self.hook()
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("cannot read", out)

    def test_hooks_json_runs_this_command(self):
        with open(os.path.join(REPO, "hooks", "hooks.json")) as f:
            spec = json.load(f)
        group = spec["hooks"]["SessionStart"][0]
        self.assertEqual(group["matcher"], "startup|resume|clear|compact")
        h = group["hooks"][0]
        self.assertEqual((h["type"], h["command"]), ("command", "python3"))
        self.assertEqual(h["args"], ["${CLAUDE_PLUGIN_ROOT}/scripts/broken_rules.py", "hook", "session-start"])
