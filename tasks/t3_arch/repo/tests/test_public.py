"""公开回归基线。一行都不许改，也不许新增 .test.py。

这些测试在「单人顺序操作」下全部通过 —— 现场报障都发生在多人/跨单位/流转时。
"""
import os, sys, sqlite3, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import db, mes  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "t.db")
        self.conn = db.fresh(self.path)

    def tearDown(self):
        self.conn.close()


class TestUnits(Base):
    def test_convert_kg_to_g(self):
        self.assertEqual(mes.to_base(self.conn, 1, 2.0, "kg"), 2000.0)

    def test_convert_g_to_g(self):
        self.assertEqual(mes.to_base(self.conn, 1, 5.0, "g"), 5.0)


class TestIssue(Base):
    def test_issue_small_amount_ok(self):
        self.assertTrue(mes.issue_material(self.conn, 1, 1000.0, "g"))

    def test_balance_decreases(self):
        mes.issue_material(self.conn, 1, 500.0, "g")
        self.assertEqual(self.conn.execute(
            "SELECT qty_base FROM item_balance WHERE item_id=1").fetchone()[0], 1500.0)


class TestTemplate(Base):
    def test_apply_returns_content(self):
        c = mes.apply_template(self.conn, 101, "TPL-A")
        self.assertIsNotNone(c)

    def test_get_content_not_none(self):
        mes.apply_template(self.conn, 101, "TPL-A")
        self.assertIsNotNone(mes.get_content(self.conn, 101))


class TestAttachments(Base):
    def test_sub_order_has_own_attachment(self):
        names = [a["name"] for a in mes.get_attachments(self.conn, "sub_order", "1-101")]
        self.assertIn("子单工艺卡.pdf", names)


class TestProcess(Base):
    def test_report_and_list(self):
        mes.report_work(self.conn, 1, 101, "w1", 10.0)
        self.assertEqual(len(mes.list_exec(self.conn, 101)), 1)

    def test_summary_matches_single_report(self):
        mes.report_work(self.conn, 1, 101, "w1", 10.0)
        self.assertEqual(mes.summary_qty(self.conn, 101), 10.0)


class TestStocktake(Base):
    def test_review_then_settle(self):
        mes.review_count(self.conn, 1, 1, 2.0, "kg", "u1")
        self.assertIsNotNone(mes.settle_count(self.conn, 1, 1))

    def test_reconcile_has_three_keys(self):
        r = mes.reconcile(self.conn, 1)
        self.assertEqual(set(r), {"ledger", "reviews", "settlement"})


class TestApprovals(Base):
    def test_four_approvals_reach_approved(self):
        for s in mes.SEGMENTS:
            mes.approve_segment(self.conn, "101", s, "u1")
        self.assertEqual(mes.board_stage(self.conn, "101"), "approved")

    def test_reject_sets_stage(self):
        mes.reject_doc(self.conn, "101", "u1")
        self.assertEqual(mes.board_stage(self.conn, "101"), "rejected")

    def test_void_is_recorded(self):
        mes.void_doc(self.conn, "101", "u1")
        n = self.conn.execute("SELECT COUNT(*) FROM approvals WHERE action='void'").fetchone()[0]
        self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
