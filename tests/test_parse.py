from helpers import HEAD, TempCase, br, entry


class SettingsTest(TempCase):
    def test_defaults_without_front_matter(self):
        settings, problems = br.parse_settings("# Broken rules\n")
        self.assertEqual(settings["sources"], br.DEFAULT_SOURCES)
        self.assertEqual(settings["timeout"], 30)
        self.assertEqual(problems, [])

    def test_custom_sources_and_timeout(self):
        text = "---\nsources: AGENTS.md, docs/*.md ,  ~/.claude/CLAUDE.md\ntimeout: 5\n---\n# x\n"
        settings, problems = br.parse_settings(text)
        self.assertEqual(settings["sources"], ["AGENTS.md", "docs/*.md", "~/.claude/CLAUDE.md"])
        self.assertEqual(settings["timeout"], 5)
        self.assertEqual(problems, [])

    def test_crlf_front_matter(self):
        settings, problems = br.parse_settings("---\r\ntimeout: 7\r\n---\r\n")
        self.assertEqual((settings["timeout"], problems), (7, []))

    def test_bad_values_are_problems(self):
        _, problems = br.parse_settings("---\ntimeout: soon\ncolour: red\nsources:\njunk line\n---\n")
        self.assertEqual(len(problems), 4, problems)
        self.assertTrue(any("timeout" in p for p in problems))
        self.assertTrue(any("colour" in p for p in problems))
        self.assertTrue(any("sources" in p for p in problems))

    def test_zero_timeout_is_a_problem(self):
        settings, problems = br.parse_settings("---\ntimeout: 0\n---\n")
        self.assertEqual(settings["timeout"], 30)
        self.assertEqual(len(problems), 1)


class RegisterTest(TempCase):
    def parse(self, body):
        return br.parse_register(self.write("BROKEN-RULES.md", HEAD + body))

    def test_entries_and_fields(self):
        es = self.parse(entry("B-001", "First", "open", check="grep -q x f.md")
                        + entry("B-002", "Second — with a dash", "fixed", fix="`abc1234`", sev="high",
                                rule='"Never add AI co-author lines" (docs/CLAUDE.md:12)'))
        self.assertEqual([e["id"] for e in es], ["B-001", "B-002"])
        a, b = es
        self.assertEqual((a["title"], a["status"], a["severity"]), ("First", "open", "low"))
        self.assertEqual(a["check"], "grep -q x f.md")
        self.assertIsNone(a["fix_commit"])
        self.assertEqual(a["last_check"], "2026-09-01 fail")
        self.assertEqual(a["problems"], [])
        self.assertEqual(b["title"], "Second — with a dash")
        self.assertEqual(b["fix_commit"], "abc1234")
        self.assertEqual(b["rule"], "Never add AI co-author lines")
        self.assertEqual(b["rule_ref"], ("docs/CLAUDE.md", 12))

    def test_fenced_example_is_not_an_entry(self):
        self.assertEqual(self.parse(""), [])

    def test_line_no_is_the_heading_line(self):
        es = self.parse(entry("B-001", "First", "open"))
        self.assertEqual(es[0]["line_no"], (HEAD.count("\n") + 1))

    def test_double_backtick_check(self):
        es = self.parse(entry("B-001", "T", "open").replace("`true`", "`` echo `x` ``"))
        self.assertEqual(es[0]["check"], "echo `x`")

    def test_problems(self):
        es = self.parse(entry("B-001", "No check", "open").replace("- **Check:** `true`\n", "")
                        + entry("B-002", "Wontfix, no check", "wontfix").replace("- **Check:** `true`\n", "")
                        + entry("B-003", "Odd status", "closed")
                        + entry("B-004", "Twin", "open") + entry("B-004", "Twin", "open")
                        + "### B-005 no status here\n- **Check:** `true`\n\n"
                        + entry("B-006", "Empty check", "open", check="—"))
        p = {e["id"]: e["problems"] for e in es if e["id"] != "B-004"}
        self.assertEqual(p["B-001"], ["no Check line"])
        self.assertEqual(p["B-002"], [])
        self.assertEqual(p["B-003"], ["unknown status 'closed'"])
        self.assertTrue(p["B-005"] and "heading" in p["B-005"][0])
        self.assertEqual(p["B-006"], ["empty Check line"])
        twins = [e for e in es if e["id"] == "B-004"]
        self.assertTrue(all("duplicate id B-004" in e["problems"] for e in twins))

    def test_rule_without_ref(self):
        es = self.parse(entry("B-001", "T", "open", rule="just text"))
        self.assertIsNone(es[0]["rule_ref"])
        self.assertEqual(es[0]["rule"], "just text")

    def test_next_id(self):
        self.assertEqual(br.next_id([]), "B-001")
        es = self.parse(entry("B-002", "a", "open") + entry("B-009", "b", "wontfix")
                        + "### B-012 no status here\n\n")
        self.assertEqual(br.next_id(es), "B-013")
