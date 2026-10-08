"""隐藏测试：模型不可见，判分时由 runner 注入。

每条对应一个现场报障。覆盖「多人/跨单位/流转」场景，而不是单人顺序操作。
"""
import os, sys, threading, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

from src import db, mes, faults  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "t.db")
        self.conn = db.fresh(self.path)

    def tearDown(self):
        self.conn.close()


class TestP1Units(Base):
    """现象一：台账 2000 g（2 kg）。需求 1.2 kg = 1200 g，应够且只扣 1200。"""
    def test_1_2kg_deducts_1200(self):
        mes.issue_material(self.conn, 1, 1.2, "kg")
        got = self.conn.execute("SELECT qty_base FROM item_balance WHERE item_id=1").fetchone()[0]
        self.assertAlmostEqual(got, 800.0, places=6)

    def test_2_5kg_should_be_rejected(self):
        self.assertFalse(mes.issue_material(self.conn, 1, 2.5, "kg"))

    def test_ledger_writes_converted_amount(self):
        mes.issue_material(self.conn, 1, 1.2, "kg")
        r = self.conn.execute("SELECT qty_base FROM ledger WHERE qty_base<0").fetchone()
        self.assertAlmostEqual(r[0], -1200.0, places=6)


class TestP2Template(Base):
    """现象二：老单内容不随新版变，新单套当前版。"""
    def test_old_order_pins_its_version(self):
        mes.apply_template(self.conn, 101, "TPL-A")
        before = mes.get_content(self.conn, 101)
        self.conn.execute("UPDATE templates SET version=3, content_json='{\"step\":\"v3\"}', is_current=1 "
                          "WHERE id=2")
        self.conn.commit()
        self.assertEqual(mes.get_content(self.conn, 101), before)

    def test_new_order_gets_current_version(self):
        self.conn.execute("INSERT INTO sub_orders(id,order_id,code,template_id,created_at) "
                          "VALUES(103,1,'WO-1-C',2,'2026-02-01T00:00:00')")
        self.conn.execute("INSERT INTO sub_order_content(id,sub_order_id,template_id,content_json) "
                          "VALUES(3,103,2,NULL)")
        self.conn.commit()
        mes.apply_template(self.conn, 103, "TPL-A")
        self.assertEqual(mes.get_content(self.conn, 103), '{"step":"new"}')


class TestP3Attachments(Base):
    """现象三：子单资料列表不得包含主单资料。"""
    def test_no_parent_leak(self):
        names = [a["name"] for a in mes.get_attachments(self.conn, "sub_order", "1-101")]
        self.assertNotIn("主单图纸.dwg", names)

    def test_parent_still_has_its_own(self):
        names = [a["name"] for a in mes.get_attachments(self.conn, "order", "1")]
        self.assertIn("主单图纸.dwg", names)

    def test_sub_order_still_has_its_own(self):
        names = [a["name"] for a in mes.get_attachments(self.conn, "sub_order", "1-101")]
        self.assertIn("子单工艺卡.pdf", names)


class TestP4Concurrency(Base):
    """现象四：共用工序并发报工。"""
    def test_same_worker_reports_are_idempotent(self):
        n = 8
        barrier = threading.Barrier(n)

        def w(_):
            c = db.connect(self.path)
            barrier.wait()
            try:
                mes.report_work(c, 1, 101, "w1", 1.0)
            finally:
                c.close()

        ts = [threading.Thread(target=w, args=(i,)) for i in range(n)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(mes.list_exec(self.conn, 101)), 1)

    def test_no_cross_order_contamination(self):
        def w(sid):
            c = db.connect(self.path)
            mes.report_work(c, 1, sid, "w9", 5.0)
            c.close()

        t1 = threading.Thread(target=w, args=(101,))
        t2 = threading.Thread(target=w, args=(102,))
        t1.start(); t2.start(); t1.join(); t2.join()
        self.assertEqual(len(mes.list_exec(self.conn, 101)), 1)
        self.assertEqual(len(mes.list_exec(self.conn, 102)), 1)

    def test_atomicity_under_injected_fault(self):
        """注入点在写入后抛异常 —— 正确实现应整体回滚，不留半成品。"""
        def boom(conn=None):
            raise RuntimeError("injected")

        faults.install("report_work", boom)
        c = db.connect(self.path)
        try:
            with self.assertRaises(RuntimeError):
                mes.report_work(c, 1, 101, "w1", 7.0)
        finally:
            faults.uninstall("report_work")
            c.close()
        self.assertEqual(len(mes.list_exec(self.conn, 101)), 0)


class TestP5Stocktake(Base):
    """现象五：三个数字要对得上，单位要换算，名字不能记错。"""
    def test_mixed_units_reconcile(self):
        mes.review_count(self.conn, 1, 1, 2.0, "kg", "overseas")
        mes.settle_count(self.conn, 1, 1)
        r = mes.reconcile(self.conn, 1)
        self.assertAlmostEqual(r["reviews"], r["settlement"], places=6)
        self.assertAlmostEqual(r["reviews"], r["ledger"], places=6)

    def test_concurrent_reviews_not_lost(self):
        n = 6
        barrier = threading.Barrier(n)

        def w(i):
            c = db.connect(self.path)
            barrier.wait()
            mes.review_count(c, 1, 1, 100.0 + i, "g", f"u{i}")
            c.close()

        ts = [threading.Thread(target=w, args=(i,)) for i in range(n)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        cnt = self.conn.execute("SELECT COUNT(*) FROM count_reviews WHERE count_id=1").fetchone()[0]
        self.assertEqual(cnt, n)

    def test_review_keeps_its_own_reviewer(self):
        mes.review_count(self.conn, 1, 1, 100.0, "g", "u1")
        mes.review_count(self.conn, 1, 1, 200.0, "g", "u2")
        rows = {r["reviewer"]: r["qty"] for r in self.conn.execute(
            "SELECT reviewer, qty FROM count_reviews WHERE count_id=1").fetchall()}
        self.assertEqual(rows.get("u1"), 100.0)
        self.assertEqual(rows.get("u2"), 200.0)


class TestP6Approvals(Base):
    """现象六：四段会签。"""
    def _fresh_doc(self, doc="201"):
        self.conn.execute("DELETE FROM approvals WHERE doc_id=?", (doc,))
        self.conn.execute("DELETE FROM approval_board WHERE doc_id=?", (doc,))
        self.conn.commit()
        return doc

    def test_reject_then_only_first_segment_not_approved(self):
        d = self._fresh_doc()
        for s in (1, 2, 3, 4):
            mes.approve_segment(self.conn, d, s, f"u{s}")
        mes.reject_doc(self.conn, d, "boss")
        mes.approve_segment(self.conn, d, 1, "u1")
        self.assertNotEqual(mes.board_stage(self.conn, d), "approved")

    def test_void_blocks_further_approval(self):
        d = self._fresh_doc()
        mes.void_doc(self.conn, d, "boss")
        mes.approve_segment(self.conn, d, 1, "u1")
        self.assertNotEqual(mes.board_stage(self.conn, d), "approved")

    def test_parallel_segments_need_both(self):
        d = self._fresh_doc()
        mes.approve_segment(self.conn, d, 1, "u1")
        mes.approve_segment(self.conn, d, 2, "u2")
        self.assertNotEqual(mes.board_stage(self.conn, d), "approved")

    def test_all_four_then_approved(self):
        d = self._fresh_doc()
        for s in (1, 2, 3, 4):
            mes.approve_segment(self.conn, d, s, f"u{s}")
        self.assertEqual(mes.board_stage(self.conn, d), "approved")

    def test_board_matches_actual(self):
        d = self._fresh_doc()
        mes.approve_segment(self.conn, d, 1, "u1")
        approved = self.conn.execute(
            "SELECT COUNT(DISTINCT segment) FROM approvals WHERE doc_id=? AND action='approve'",
            (d,)).fetchone()[0]
        stage = mes.board_stage(self.conn, d)
        self.assertEqual(stage, "approved" if approved >= 4 else stage)


if __name__ == "__main__":
    unittest.main()
