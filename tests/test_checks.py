import os
import time

from helpers import TempCase, br


def mk(status, check="true", fix=None, bid="B-100"):
    return {"id": bid, "status": status, "check": check, "fix_commit": fix, "problems": []}


class RunCheckTest(TempCase):
    def test_results(self):
        self.assertEqual(br.run_check("true", self.tmp, 5)[0], "pass")
        self.assertEqual(br.run_check("false", self.tmp, 5)[0], "fail")
        self.assertEqual(br.run_check("exit 3", self.tmp, 5)[0], "fail")
        self.assertEqual(br.run_check("", self.tmp, 5)[0], "error")

    def test_command_not_found_is_error(self):
        result, detail = br.run_check("no-such-command-xyz", self.tmp, 5)
        self.assertEqual(result, "error")
        self.assertIn("127", detail)
        self.assertEqual(br.run_check(self.write("x.sh", "true"), self.tmp, 5)[0], "error")  # 126

    def test_cwd_is_root(self):
        self.write("marker.txt")
        self.assertEqual(br.run_check("test -f marker.txt", self.tmp, 5)[0], "pass")

    def test_timeout_is_error_and_quick(self):
        t0 = time.monotonic()
        result, detail = br.run_check("sleep 5 | cat", self.tmp, 1)
        self.assertEqual(result, "error")
        self.assertIn("timeout", detail)
        self.assertLess(time.monotonic() - t0, 3)

    def test_stdin_is_at_eof(self):
        t0 = time.monotonic()
        self.assertEqual(br.run_check("read x", self.tmp, 5)[0], "fail")
        self.assertLess(time.monotonic() - t0, 3)

    def test_fail_detail_has_last_output_line(self):
        _, detail = br.run_check("echo first; echo 'last words'; exit 1", self.tmp, 5)
        self.assertIn("last words", detail)


class MovesTest(TempCase):
    def test_table(self):
        table = [("fixed", True, True, "verified"), ("fixed", False, True, "reopened"),
                 ("fixed", False, None, "reopened"), ("verified", False, True, "reopened"),
                 ("open", True, True, "open"), ("open", True, None, "open"),
                 ("open", False, None, "open"), ("reopened", True, True, "verified"),
                 ("reopened", False, True, "reopened"), ("verified", True, True, "verified"),
                 ("fixed", True, None, "fixed"), ("fixed", True, False, "fixed"),
                 ("reopened", True, None, "reopened"), ("reopened", True, False, "reopened"),
                 ("wontfix", True, True, "wontfix"), ("wontfix", False, None, "wontfix")]
        for status, passed, fix_ok, want in table:
            self.assertEqual(br.next_status(status, passed, fix_ok), want, (status, passed, fix_ok))


class HistoryTest(TempCase):
    def setUp(self):
        super().setUp()
        self.good = self.repo()
        home = self.git("rev-parse", "--abbrev-ref", "HEAD")
        self.git("checkout", "-q", "-b", "side")
        self.git("commit", "-q", "--allow-empty", "-m", "side only")
        self.side = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", home)

    def test_fix_in_history(self):
        self.assertIs(br.fix_in_history(self.good, self.tmp), True)
        self.assertIs(br.fix_in_history(self.good[:7], self.tmp), True)
        self.assertIs(br.fix_in_history(self.side, self.tmp), False)
        self.assertIs(br.fix_in_history("deadbee", self.tmp), False)
        self.assertIs(br.fix_in_history("--help", self.tmp), False)
        self.assertIsNone(br.fix_in_history(None, self.tmp))

    def test_outside_git_nothing_resolves(self):
        other = os.path.join(self.tmp, "..", os.path.basename(self.tmp) + "-nogit")
        os.makedirs(other)
        try:
            self.assertIs(br.fix_in_history(self.good, other), False)
        finally:
            os.rmdir(other)

    def test_check_entry(self):
        r = br.check_entry(mk("fixed", "true", self.good), self.tmp, 5)
        self.assertEqual((r[0], r[2]), ("pass", "verified"))
        r = br.check_entry(mk("fixed", "true", "deadbee"), self.tmp, 5)
        self.assertEqual((r[0], r[2]), ("error", "fixed"))
        self.assertIn("deadbee", r[1])
        for st in ("fixed", "reopened"):
            r = br.check_entry(mk(st, "true", self.side), self.tmp, 5)
            self.assertEqual((r[0], r[2]), ("error", st))
        r = br.check_entry(mk("fixed", "true", None), self.tmp, 5)
        self.assertEqual((r[0], r[2]), ("error", "fixed"))
        self.assertIn("no fix commit", r[1])
        r = br.check_entry(mk("fixed", "false", "deadbee"), self.tmp, 5)
        self.assertEqual((r[0], r[2]), ("fail", "reopened"))
        r = br.check_entry(mk("verified", "no-such-command-xyz", self.good), self.tmp, 5)
        self.assertEqual((r[0], r[2]), ("error", "verified"))

    def test_check_all(self):
        entries = [mk("open", "true", bid="B-001"), mk("fixed", "true", self.good, "B-002"),
                   mk("fixed", "false", self.good, "B-003"), mk("open", "false", bid="B-004"),
                   mk("wontfix", "touch ran", bid="B-005"),
                   dict(mk("open", bid="B-006"), problems=["no Check line"])]
        results, lines, attention = br.check_all(entries, self.tmp, 5)
        self.assertTrue(attention)
        self.assertIn("NOTE B-001 open but check passes; record the fix commit", lines)
        self.assertTrue(any(l.startswith("VERIFIED B-002") for l in lines))
        self.assertTrue(any(l.startswith("REOPENED B-003") for l in lines))
        self.assertIn("ERROR B-006 no Check line", lines)
        self.assertFalse(any("B-004" in l or "B-005" in l for l in lines))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "ran")))
        self.assertEqual(results["B-002"], ("verified", "pass"))
        self.assertEqual(results["B-004"], ("open", "fail"))
        self.assertNotIn("B-005", results)
        self.assertNotIn("B-006", results)

    def test_quiet_run_needs_no_attention(self):
        entries = [mk("open", "false", bid="B-001"), mk("verified", "true", self.good, "B-002")]
        _, lines, attention = br.check_all(entries, self.tmp, 5)
        self.assertEqual((lines, attention), ([], False))

    def test_summary(self):
        entries = [mk("open", bid="B-001"), mk("fixed", bid="B-002"), mk("wontfix", bid="B-003")]
        line = br.summary(entries, {"B-002": ("verified", "pass")})
        self.assertEqual(line, "open 1 · fixed 0 · verified 1 · reopened 0 · wontfix 1")
