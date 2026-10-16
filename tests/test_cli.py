import json
import os

from helpers import HEAD, TempCase, br, entry

AGENTS = "# Rules\n\n- Never add AI co-author lines.\n- Keep subjects under 72 characters.\n"


class CliTest(TempCase):
    def setUp(self):
        super().setUp()
        self.good = self.repo()
        self.write("AGENTS.md", AGENTS)
        self.reg = os.path.join(self.tmp, "BROKEN-RULES.md")

    def test_init_creates_a_clean_register_once(self):
        code, out = self.cli("init")
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isfile(self.reg))
        self.assertEqual(self.cli("lint"), (0, ""))
        self.assertEqual(self.cli("run")[0], 0)
        code, out = self.cli("init")
        self.assertEqual(code, 1)
        self.assertIn("already exists", out)

    def test_file_then_fixed_then_update(self):
        self.cli("init")
        code, out = self.cli("file", "--title", "Co-author line", "--rule", "Never add AI co-author lines",
                             "--severity", "high", "--evidence", "commit abc", "--fix", "hook",
                             "--check", "test -f fixed.txt")
        self.assertEqual(code, 0, out)
        self.assertIn("FILED B-001", out)
        self.assertIn("AGENTS.md:3", out)
        code, out = self.cli("file", "--title", "x", "--rule", "Never add AI co-author lines",
                             "--severity", "high", "--evidence", "e", "--fix", "f", "--check", "true")
        self.assertEqual(code, 1)
        self.assertIn("passes now", out)

        self.write("fixed.txt")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fix")
        sha = self.git("rev-parse", "--short", "HEAD")
        code, out = self.cli("fixed", "B-001", sha)
        self.assertEqual(code, 0, out)
        self.assertEqual(br.parse_register(self.reg)[0]["status"], "fixed")

        before = self.raw(self.reg)
        code, out = self.cli("run")
        self.assertEqual(code, 0, out)
        self.assertIn("VERIFIED B-001", out)
        self.assertIn("open 0 · fixed 0 · verified 1 · reopened 0 · wontfix 0", out)
        self.assertEqual(self.raw(self.reg), before, "run must not write")

        code, out = self.cli("update")
        self.assertEqual(code, 0, out)
        self.assertEqual(br.parse_register(self.reg)[0]["status"], "verified")
        code, out = self.cli("update")
        self.assertNotIn("VERIFIED", out)

        os.remove(os.path.join(self.tmp, "fixed.txt"))
        code, out = self.cli("update")
        self.assertEqual(code, 1)
        self.assertIn("REOPENED B-001", out)
        self.assertEqual(br.parse_register(self.reg)[0]["status"], "reopened")

    def test_fixed_refusals(self):
        self.write("BROKEN-RULES.md", HEAD + entry("B-001", "A", "open") + entry("B-002", "B", "verified"))
        home = self.git("rev-parse", "--abbrev-ref", "HEAD")
        self.git("checkout", "-q", "-b", "side")
        self.git("commit", "-q", "--allow-empty", "-m", "side")
        side = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", home)
        for args in (("B-001", side), ("B-001", "deadbee"), ("B-002", self.good), ("B-404", self.good)):
            code, out = self.cli("fixed", *args)
            self.assertEqual(code, 1, (args, out))
            self.assertIn("ERROR", out)
        self.assertEqual([e["status"] for e in br.parse_register(self.reg)], ["open", "verified"])

    def test_check_one(self):
        self.write("BROKEN-RULES.md", HEAD + entry("B-001", "A", "open", check="false")
                   + entry("B-002", "B", "wontfix", extra="- **Reason:** n/a\n"))
        self.assertEqual(self.cli("check", "B-001")[0], 1)
        self.assertIn("FAIL B-001", self.cli("check", "B-001")[1])
        self.assertEqual(self.cli("check", "B-002")[0], 0)
        code, out = self.cli("check", "B-404")
        self.assertEqual(code, 1)
        self.assertIn("ERROR B-404", out)

    def test_lint(self):
        self.write("BROKEN-RULES.md", HEAD.replace("timeout: 30", "timeout: 30\ncolour: red")
                   + entry("B-001", "Good", "open", rule='"Never add AI co-author lines." (AGENTS.md:3)')
                   + entry("B-002", "Rule edited away", "open", rule='"Never push on Fridays" (AGENTS.md:3)')
                   + entry("B-003", "Bad severity", "open", sev="urgent",
                           rule='"Keep subjects under 72 characters." (AGENTS.md:4)')
                   + entry("B-004", "No reason", "wontfix", rule='"Keep subjects" (AGENTS.md:4)')
                   + entry("B-005", "Gone file", "open", rule='"x" (GONE.md:1)')
                   + entry("B-006", "No rule", "open").replace('- **Rule:** "Example" (AGENTS.md:1)\n', ""))
        code, out = self.cli("lint")
        self.assertEqual(code, 1)
        self.assertNotIn("B-001", out)
        for want in ("colour", "B-002 rule no longer in AGENTS.md", "B-003 severity", "B-004 wontfix",
                     "B-005", "B-006 no Rule line"):
            self.assertIn(want, out)

    def test_register_found_from_a_subfolder(self):
        self.cli("init")
        sub = os.path.join(self.tmp, "deep", "er")
        os.makedirs(sub)
        self.assertEqual(self.cli("next-id", cwd=sub), (0, "B-001\n"))

    def test_register_overrides(self):
        other = self.write("elsewhere/rules.md", HEAD + entry("B-007", "A", "open"))
        self.assertEqual(self.cli("--register", other, "next-id")[1].strip(), "B-008")
        self.assertEqual(self.cli("next-id", env={"BROKEN_RULES_FILE": other})[1].strip(), "B-008")

    def test_missing_register(self):
        for cmd in ("run", "update", "lint", "next-id"):
            code, out = self.cli(cmd)
            self.assertEqual(code, 1, cmd)
            self.assertIn("no register", out)

    def test_json_written_on_every_path(self):
        js = self.write("out.json", '[{"stale": true}]')
        self.cli("run", "--json", js)
        with open(js) as f:
            self.assertEqual(json.load(f), [])
        self.write("BROKEN-RULES.md", HEAD + entry("B-001", "A", "open", check="false"))
        self.cli("run", "--json", js)
        with open(js) as f:
            rows = json.load(f)
        self.assertEqual([(r["id"], r["status"], r["new_status"], r["result"]) for r in rows],
                         [("B-001", "open", "open", "fail")])

    def test_settings_problems_need_attention(self):
        self.write("BROKEN-RULES.md", HEAD.replace("timeout: 30", "timeout: never"))
        code, out = self.cli("run")
        self.assertEqual(code, 1)
        self.assertIn("ERROR settings", out)
