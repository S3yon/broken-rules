from helpers import HEAD, TempCase, br, entry


class UpdateTest(TempCase):
    def test_only_status_and_last_check_change(self):
        text = (HEAD
                + entry("B-001", "Keeps — dashes, naïve café", "fixed",
                        extra="- **Evidence:** ends in spaces   \n")
                + entry("B-002", "Stays", "open", last="2026-09-02 fail")
                + entry("B-003", "Reopens", "verified", last="2026-09-03 pass"))
        path = self.write("BROKEN-RULES.md", text)
        br.update_register(path, {"B-001": ("verified", "pass"), "B-003": ("reopened", "fail"),
                                  "B-099": ("verified", "pass")}, "2026-10-16")
        want = (text.replace("naïve café — fixed", "naïve café — verified")
                .replace("### B-003 Reopens — verified", "### B-003 Reopens — reopened")
                .replace("- **Last check:** 2026-09-01 fail", "- **Last check:** 2026-10-16 pass")
                .replace("- **Last check:** 2026-09-03 pass", "- **Last check:** 2026-10-16 fail"))
        self.assertEqual(self.raw(path), want.encode("utf-8"))
        self.assertIn(b"### B-099 Example in a fence \xe2\x80\x94 open", self.raw(path))

    def test_missing_last_check_is_added_after_the_entry(self):
        text = HEAD + entry("B-001", "A", "open").replace("- **Last check:** 2026-09-01 fail\n", "") \
            + entry("B-002", "B", "open")
        path = self.write("BROKEN-RULES.md", text)
        br.update_register(path, {"B-001": ("open", "fail")}, "2026-10-16")
        want = text.replace("- **Fix commit:** —\n\n### B-002",
                            "- **Fix commit:** —\n- **Last check:** 2026-10-16 fail\n\n### B-002")
        self.assertEqual(self.raw(path), want.encode("utf-8"))

    def test_entry_at_end_with_no_final_newline(self):
        path = self.write("BROKEN-RULES.md", "### B-001 Ends the file — fixed\n- **Check:** `true`")
        br.update_register(path, {"B-001": ("verified", "pass")}, "2026-10-16")
        self.assertEqual(self.raw(path), "### B-001 Ends the file — verified\n- **Check:** `true`\n"
                         "- **Last check:** 2026-10-16 pass\n".encode("utf-8"))

    def test_crlf_is_kept(self):
        text = (HEAD + entry("B-001", "A", "fixed")).replace("\n", "\r\n")
        path = self.write("BROKEN-RULES.md", text, newline="")
        br.update_register(path, {"B-001": ("verified", "pass")}, "2026-10-16")
        out = self.raw(path)
        self.assertNotIn(b"\n", out.replace(b"\r\n", b""))
        self.assertIn("### B-001 A — verified\r\n".encode("utf-8"), out)
        self.assertIn(b"- **Last check:** 2026-10-16 pass\r\n", out)

    def test_crlf_added_line_uses_crlf(self):
        text = (HEAD + entry("B-001", "A", "open")).replace("- **Last check:** 2026-09-01 fail\n", "")
        path = self.write("BROKEN-RULES.md", text.replace("\n", "\r\n"), newline="")
        br.update_register(path, {"B-001": ("open", "fail")}, "2026-10-16")
        out = self.raw(path)
        self.assertNotIn(b"\n", out.replace(b"\r\n", b""))
        self.assertIn(b"- **Last check:** 2026-10-16 fail\r\n", out)

    def test_set_fixed(self):
        text = HEAD + entry("B-001", "A", "open") + entry("B-002", "B", "reopened", fix="abc1234")
        path = self.write("BROKEN-RULES.md", text)
        br.set_fixed(path, "B-002", "def5678")
        want = (text.replace("### B-002 B — reopened", "### B-002 B — fixed")
                .replace("- **Fix commit:** abc1234", "- **Fix commit:** def5678"))
        self.assertEqual(self.raw(path), want.encode("utf-8"))


class AppendTest(TempCase):
    def test_format_and_append(self):
        text = br.format_entry("B-001", "Commit carried a co-author line", "Never add AI co-author lines",
                               ("CLAUDE.md", 12), "high", "2026-10-16", "commit 3f2a91c",
                               "a commit-msg hook", "! git log -1 --format=%B | grep -q x")
        self.assertEqual(text, (
            "### B-001 Commit carried a co-author line — open\n"
            "- **Rule:** \"Never add AI co-author lines\" (CLAUDE.md:12)\n"
            "- **Severity:** high · **Found:** 2026-10-16\n"
            "- **Evidence:** commit 3f2a91c\n"
            "- **Fix:** a commit-msg hook\n"
            "- **Check:** `! git log -1 --format=%B | grep -q x`\n"
            "- **Fix commit:** —\n"
            "- **Last check:** 2026-10-16 fail\n"))
        path = self.write("BROKEN-RULES.md", HEAD + "\n\n")
        br.append_entry(path, text)
        self.assertEqual(self.raw(path), (HEAD + text).encode("utf-8"))   # one blank line before
        es = br.parse_register(path)
        self.assertEqual([(e["id"], e["status"], e["problems"]) for e in es], [("B-001", "open", [])])
        self.assertEqual(es[0]["rule_ref"], ("CLAUDE.md", 12))

    def test_backticks_in_check_round_trip(self):
        text = br.format_entry("B-001", "T", "R", ("A.md", 1), "low", "2026-10-16", "e", "f",
                               "echo `date`")
        path = self.write("BROKEN-RULES.md", HEAD)
        br.append_entry(path, text)
        self.assertEqual(br.parse_register(path)[0]["check"], "echo `date`")

    def test_newlines_in_fields_are_flattened(self):
        text = br.format_entry("B-001", "two\nlines", "R", ("A.md", 1), "low", "2026-10-16",
                               "line one\nline two", "f", "true")
        self.assertIn("### B-001 two lines — open\n", text)
        self.assertIn("- **Evidence:** line one line two\n", text)

    def test_append_after_entry_with_no_final_newline(self):
        path = self.write("BROKEN-RULES.md", "### B-001 A — open\n- **Check:** `true`")
        br.append_entry(path, br.format_entry("B-002", "T", "R", ("A.md", 1), "low", "2026-10-16",
                                              "e", "f", "true"))
        self.assertEqual([e["id"] for e in br.parse_register(path)], ["B-001", "B-002"])
        self.assertIn(b"`true`\n\n### B-002", self.raw(path))

    def test_append_keeps_trailing_spaces_of_the_last_line(self):
        path = self.write("BROKEN-RULES.md", "### B-001 A — open\n- **Evidence:** spaces   \n\n\n")
        br.append_entry(path, br.format_entry("B-002", "T", "R", ("A.md", 1), "low", "2026-10-16",
                                              "e", "f", "true"))
        self.assertIn(b"spaces   \n\n### B-002", self.raw(path))
