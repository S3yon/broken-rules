import os

from helpers import HEAD, TempCase, br

AGENTS = """# Rules

- **No AI credit anywhere**: no co-author trailers, no "generated with" lines, in
  commits or PR text.
- Never run (rm -rf *) outside a temp folder.
- Run `git pull` from the repo root; never `git -C`.
"""


class FindRuleTest(TempCase):
    def setUp(self):
        super().setUp()
        self.write("AGENTS.md", AGENTS)

    def find(self, quote, sources=("AGENTS.md",), source=None):
        return br.find_rule(quote, self.tmp, list(sources), source)

    def test_quote_across_a_wrapped_line(self):
        self.assertEqual(self.find('no "generated with" lines, in commits or PR text'), ("AGENTS.md", 3))

    def test_markdown_emphasis_and_ticks_are_ignored(self):
        self.assertEqual(self.find("No AI credit anywhere: no co-author trailers"), ("AGENTS.md", 3))
        self.assertEqual(self.find("never git -C"), ("AGENTS.md", 6))

    def test_regex_characters_match_literally(self):
        self.assertEqual(self.find("Never run (rm -rf *) outside"), ("AGENTS.md", 5))
        with self.assertRaises(br.RuleError):
            self.find("Never run (rm -rf .) outside")

    def test_case_matters(self):
        with self.assertRaises(br.RuleError):
            self.find("never run (rm -rf *)")

    def test_not_found_names_what_was_searched(self):
        with self.assertRaises(br.RuleError) as cm:
            self.find("Always deploy on Fridays")
        self.assertIn("AGENTS.md", str(cm.exception))

    def test_no_source_files(self):
        with self.assertRaises(br.RuleError) as cm:
            self.find("x", sources=["nothing/*.md"])
        self.assertIn("no source files", str(cm.exception))

    def test_two_files_is_ambiguous(self):
        self.write("docs/CLAUDE.md", "Never run (rm -rf *) outside a temp folder.\n")
        with self.assertRaises(br.RuleError) as cm:
            self.find("Never run (rm -rf *)", sources=["AGENTS.md", "**/CLAUDE.md"])
        self.assertIn("AGENTS.md", str(cm.exception))
        self.assertIn("docs/CLAUDE.md", str(cm.exception))
        self.assertEqual(self.find("Never run (rm -rf *)", source="docs/CLAUDE.md"), ("docs/CLAUDE.md", 1))

    def test_default_sources_find_skills_and_hidden_folders(self):
        self.write(".claude/skills/publish/SKILL.md", "Only publish after an explicit go.\n")
        self.write("node_modules/pkg/AGENTS.md", "Only publish after an explicit go.\n")
        self.assertEqual(self.find("explicit go", sources=br.DEFAULT_SOURCES),
                         (".claude/skills/publish/SKILL.md", 1))

    def test_missing_source_file(self):
        with self.assertRaises(br.RuleError):
            self.find("x", source="GONE.md")

    def test_home_source_is_shown_with_tilde(self):
        home = os.path.expanduser("~")
        ref = br.display_path(os.path.join(home, "x", "CLAUDE.md"), self.tmp)
        self.assertEqual(ref, os.path.join("~", "x", "CLAUDE.md"))


class FileBreakTest(TempCase):
    def setUp(self):
        super().setUp()
        self.write("AGENTS.md", AGENTS)
        self.reg = self.write("BROKEN-RULES.md", HEAD)
        self.settings = {"sources": ["AGENTS.md"], "timeout": 2}

    def file(self, **kw):
        fields = dict(title="Commit had a co-author line", rule="no co-author trailers",
                      severity="high", evidence="commit abc1234", fix="a commit-msg hook",
                      check="false", today="2026-10-16")
        fields.update(kw)
        return br.file_break(self.reg, self.tmp, self.settings, **fields)

    def test_files_with_next_id(self):
        bid, ref = self.file()
        self.assertEqual((bid, ref), ("B-001", ("AGENTS.md", 3)))
        e = br.parse_register(self.reg)[0]
        self.assertEqual((e["id"], e["status"], e["check"], e["fix_commit"], e["last_check"]),
                         ("B-001", "open", "false", None, "2026-10-16 fail"))
        self.assertEqual(e["rule"], "no co-author trailers")
        self.assertEqual(self.file()[0], "B-002")

    def test_refuses_a_check_that_passes(self):
        with self.assertRaises(br.FileError) as cm:
            self.file(check="true")
        self.assertIn("passes now", str(cm.exception))
        self.assertEqual(br.parse_register(self.reg), [])

    def test_refuses_a_check_that_cannot_run(self):
        for check in ("no-such-command-xyz", "sleep 5"):
            with self.assertRaises(br.FileError) as cm:
                self.file(check=check)
            self.assertIn("could not run", str(cm.exception))
        self.assertEqual(br.parse_register(self.reg), [])

    def test_refuses_bad_input(self):
        for kw in ({"severity": "urgent"}, {"title": " "}, {"check": "false\nfalse"},
                   {"rule": "a rule nobody wrote"}):
            with self.assertRaises(br.FileError):
                self.file(**kw)
        self.assertEqual(br.parse_register(self.reg), [])

    def test_refuses_without_a_register(self):
        os.remove(self.reg)
        with self.assertRaises(br.FileError) as cm:
            self.file()
        self.assertIn("init", str(cm.exception))

    def test_register_is_not_a_rule_source(self):
        self.settings["sources"] = ["*.md"]
        self.write("BROKEN-RULES.md", HEAD.replace("# Broken rules", "# no co-author trailers here"))
        self.assertEqual(self.file()[1], ("AGENTS.md", 3))
