import os
import re
import shutil
import subprocess

from helpers import REPO, TempCase, br

RECIPES = os.path.join(REPO, "docs", "recipes.md")
WHOLE_ENV = r"environ\.(items|copy|keys|values)\(|\*\*os\.environ|dict\(os\.environ"


class DemoTest(TempCase):
    def test_demo_runs_the_whole_loop(self):
        r = subprocess.run(["bash", os.path.join(REPO, "examples", "demo.sh"), "--keep"],
                           capture_output=True, text=True, timeout=120)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        work = re.search(r"^Kept: (.+)$", out, re.M).group(1)
        self.addCleanup(shutil.rmtree, work, True)
        keep = os.path.join(work, "BROKEN-RULES.md")
        for want in ("FILED B-001", "FILED B-004", "ERROR check passes now",
                     "VERIFIED B-001 check passes; fix commit", "VERIFIED B-003",
                     "REOPENED B-002", "open 1 · fixed 0 · verified 3 · reopened 0 · wontfix 0",
                     "open 1 · fixed 0 · verified 2 · reopened 1 · wontfix 0",
                     "BROKEN RULES: 2 rules", '--title "Web reader has no page-text-is-data line"'):
            self.assertIn(want, out)
        self.assertNotIn(REPO, out)
        entries = br.parse_register(keep)
        self.assertEqual([(e["id"], e["status"]) for e in entries],
                         [("B-001", "verified"), ("B-002", "reopened"), ("B-003", "verified"),
                          ("B-004", "open")])
        self.assertTrue(all(e["problems"] == [] for e in entries))

    def test_example_register_is_the_demo_output_format(self):
        entries = br.parse_register(os.path.join(REPO, "examples", "BROKEN-RULES.md"))
        self.assertEqual([e["status"] for e in entries], ["verified", "reopened", "verified", "open"])


class DirectoryChecksTest(TempCase):
    """What the plugin directory's scanner holds for review: an environment variable read by a
    computed name, or the whole environment, as a possible credential; inline Python, or a
    command that copies to a path from its arguments, as possible data leaving the machine."""

    def test_env_vars_are_read_by_literal_name(self):
        with open(os.path.join(REPO, "scripts", "broken_rules.py"), encoding="utf-8") as f:
            names = re.findall(r"environ\.get\(([^,)]*)", f.read())
        self.assertTrue(names)
        for name in names:
            self.assertRegex(name, r'^"[A-Z_]+"$')

    def test_demo_has_no_inline_python(self):
        with open(os.path.join(REPO, "examples", "demo.sh"), encoding="utf-8") as f:
            self.assertNotIn("python3 -c", f.read())

    def test_no_code_reads_the_whole_environment(self):
        for folder, _, files in os.walk(REPO):
            for name in files:
                if name.endswith(".py"):
                    with open(os.path.join(folder, name), encoding="utf-8") as f:
                        self.assertNotRegex(f.read(), WHOLE_ENV, name)

    def test_demo_copies_or_sends_nothing_out_of_its_folder(self):
        with open(os.path.join(REPO, "examples", "demo.sh"), encoding="utf-8") as f:
            self.assertIsNone(re.search(r"^\s*(cp|mv|scp|rsync|curl|wget)\s", f.read(), re.M))


class RecipesTest(TempCase):
    def test_recipes_without_placeholders_run(self):
        with open(RECIPES, encoding="utf-8") as f:
            cmds = re.findall(r"```sh\n(.+?)\n```", f.read())
        self.assertGreaterEqual(len(cmds), 8)
        self.repo()
        self.git("commit", "-q", "--allow-empty", "-m", "feat(x): a normal subject")
        runnable = [c for c in cmds if "<" not in c]
        self.assertGreaterEqual(len(runnable), 4)
        for cmd in runnable:
            result, detail = br.run_check(cmd, self.tmp, 10)
            self.assertNotEqual(result, "error", (cmd, detail))
