"""MES 业务层。功能齐、公开测试全绿，但现场报障未修。

六个现象对应的实现都在这里。修改本文件是允许的（不在冻结清单内）。
"""
import datetime
from . import faults

NOW = lambda: datetime.datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ 单位
def to_base(conn, item_id, qty, unit):
    """把 qty 从 unit 换算到物料的基准单位（g）。"""
    row = conn.execute(
        "SELECT factor FROM unit_conversions WHERE item_id=? AND from_unit=? AND to_unit="
        "(SELECT base_unit FROM items WHERE id=?)", (item_id, unit, item_id)).fetchone()
    return qty * (row["factor"] if row else 1.0)


# ------------------------------------------------------------------ 现象一：领料判定
def issue_material(conn, item_id, demand_qty, demand_unit):
    """判断库存是否够发。够则扣减台账，返回 True。"""
    bal = conn.execute("SELECT qty_base FROM item_balance WHERE item_id=?", (item_id,)).fetchone()
    if bal is None:
        total = conn.execute("SELECT COALESCE(SUM(qty_base),0) FROM ledger WHERE item_id=?",
                             (item_id,)).fetchone()[0]
        conn.execute("INSERT OR REPLACE INTO item_balance(item_id,qty_base) VALUES(?,?)", (item_id, total))
        bal = conn.execute("SELECT qty_base FROM item_balance WHERE item_id=?", (item_id,)).fetchone()
    need = demand_qty  # BUG-1：需求未换算到基准单位；且扣减/入账同样用未换算值，污染台账
    if bal["qty_base"] < need:
        return False
    conn.execute("UPDATE item_balance SET qty_base=qty_base-? WHERE item_id=?", (need, item_id))
    conn.execute("INSERT INTO ledger(item_id,qty_base,unit,ts) VALUES(?,?,?,?)",
                 (item_id, -need, demand_unit, NOW()))
    conn.commit()
    return True


# ------------------------------------------------------------------ 现象二：模板快照
def apply_template(conn, sub_order_id, template_code):
    """给子单套用工艺模板内容。"""
    row = conn.execute(
        "SELECT id, content_json FROM templates WHERE code=? ORDER BY version ASC LIMIT 1",
        (template_code,)).fetchone()  # BUG-2a：取了最小版本，新建单子套出旧内容
    if not row:
        return None
    conn.execute("UPDATE sub_order_content SET template_id=?, content_json=NULL WHERE sub_order_id=?",
                 (row["id"], sub_order_id))
    conn.commit()
    return row["content_json"]


def get_content(conn, sub_order_id):
    """读取子单的套用内容。"""
    r = conn.execute(
        "SELECT c.content_json, t.content_json AS tpl "
        "FROM sub_order_content c JOIN templates t ON t.code=(SELECT code FROM templates WHERE id=c.template_id) "
        "WHERE c.sub_order_id=? ORDER BY t.version DESC LIMIT 1", (sub_order_id,)).fetchone()
    # BUG-2b：读取时按模板最新版本解析，老单子内容跟着新版变
    if r and r["content_json"]:
        return r["content_json"]
    return r["tpl"] if r else None


# ------------------------------------------------------------------ 现象三：附件归属
def get_attachments(conn, owner_type, owner_id):
    # BUG-3：用主单号前缀去捞资料，且丢掉了 owner_type 过滤 —— 主单的图纸会被当成子单自己的
    prefix = owner_id.split("-")[0]
    r = conn.execute("SELECT * FROM attachments WHERE owner_id LIKE ?", (f"{prefix}%",)).fetchall()
    return [dict(x) for x in r]


# ------------------------------------------------------------------ 现象四：共用工序报工
def report_work(conn, segment_id, sub_order_id, worker_id, qty):
    """共用工序报工。同一人同一工序重复提交应合并为一条。"""
    dup = conn.execute(
        "SELECT id FROM process_exec WHERE segment_id=? AND sub_order_id=? AND worker_id=?",
        (segment_id, sub_order_id, worker_id)).fetchone()
    if dup:
        conn.execute("UPDATE process_exec SET qty=?, ts=? WHERE id=?", (qty, NOW(), dup["id"]))
    else:
        conn.execute("INSERT INTO process_exec(segment_id,sub_order_id,worker_id,qty,ts) VALUES(?,?,?,?,?)",
                     (segment_id, sub_order_id, worker_id, qty, NOW()))
    conn.commit()          # BUG-4a：先提交，注入点在后 —— 中断后留下半成品
    faults.before_write("report_work", conn)
    refresh_progress(conn, sub_order_id)


def refresh_progress(conn, sub_order_id):
    tot = conn.execute("SELECT COALESCE(SUM(qty),0) FROM process_exec WHERE sub_order_id=?",
                       (sub_order_id,)).fetchone()[0]
    conn.execute("INSERT OR REPLACE INTO order_progress(sub_order_id,done_qty,last_ts) VALUES(?,?,?)",
                 (sub_order_id, tot, NOW()))
    conn.commit()          # BUG-4b：汇总与明细分两次提交，中途读到不一致


def list_exec(conn, sub_order_id):
    r = conn.execute("SELECT * FROM process_exec WHERE sub_order_id=? ORDER BY id", (sub_order_id,)).fetchall()
    return [dict(x) for x in r]


def summary_qty(conn, sub_order_id):
    r = conn.execute("SELECT done_qty FROM order_progress WHERE sub_order_id=?", (sub_order_id,)).fetchone()
    return r["done_qty"] if r else 0.0


# ------------------------------------------------------------------ 现象五：盘点
def review_count(conn, count_id, item_id, qty, unit, reviewer):
    """复核录入。同一复核人对同一物料重复录入应覆盖自己那条。"""
    exist = conn.execute(
        "SELECT id FROM count_reviews WHERE count_id=? AND item_id=? AND reviewer=?",
        (count_id, item_id, reviewer)).fetchone()
    if exist:
        # BUG-5a：更新的是「最后一条」，不是本人那条 —— 录的数覆盖到别人名下
        conn.execute("UPDATE count_reviews SET qty=?, unit=? WHERE id="
                     "(SELECT id FROM count_reviews WHERE count_id=? AND item_id=? ORDER BY id DESC LIMIT 1)",
                     (qty, unit, count_id, item_id))
    else:
        conn.execute("INSERT INTO count_reviews(count_id,item_id,qty,unit,reviewer,ts) VALUES(?,?,?,?,?,?)",
                     (count_id, item_id, qty, unit, reviewer, NOW()))
    conn.commit()
    return True


def settle_count(conn, count_id, item_id):
    r = conn.execute("SELECT qty, unit FROM count_reviews WHERE count_id=? AND item_id=? "
                     "ORDER BY id DESC LIMIT 1", (count_id, item_id)).fetchone()
    if not r:
        return None
    base = r["qty"]  # BUG-5b：直接把录入值当基准量，未做单位换算
    conn.execute("INSERT INTO count_settlements(count_id,item_id,final_qty_base) VALUES(?,?,?)",
                 (count_id, item_id, base))
    conn.commit()
    return base


def reconcile(conn, item_id):
    ledger = conn.execute("SELECT COALESCE(SUM(qty_base),0) FROM ledger WHERE item_id=?", (item_id,)).fetchone()[0]
    reviews = conn.execute(
        "SELECT COALESCE(SUM(qty * CASE WHEN unit='kg' THEN 1000.0 ELSE 1.0 END),0) "
        "FROM count_reviews WHERE item_id=?", (item_id,)).fetchone()[0]
    settle = conn.execute(
        "SELECT COALESCE(SUM(final_qty_base),0) FROM count_settlements WHERE item_id=?", (item_id,)).fetchone()[0]
    return {"ledger": ledger, "reviews": reviews, "settlement": settle}


# ------------------------------------------------------------------ 现象六：四段会签
SEGMENTS = [1, 2, 3, 4]  # 初审 / 并行段 A / 并行段 B / 终审


def _board(conn, doc_id):
    r = conn.execute("SELECT * FROM approval_board WHERE doc_id=?", (doc_id,)).fetchone()
    if not r:
        conn.execute("INSERT INTO approval_board(doc_id,stage,approved_segments) VALUES(?,?,?)",
                     (doc_id, "draft", 0))
        conn.commit()
        r = conn.execute("SELECT * FROM approval_board WHERE doc_id=?", (doc_id,)).fetchone()
    return r


def approve_segment(conn, doc_id, segment, actor):
    conn.execute("INSERT INTO approvals(doc_type,doc_id,segment,action,actor,ts) VALUES(?,?,?,?,?,?)",
                 ("sub_order", doc_id, segment, "approve", actor, NOW()))
    b = _board(conn, doc_id)
    n = b["approved_segments"] + 1
    conn.execute("UPDATE approval_board SET approved_segments=? WHERE doc_id=?", (n, doc_id))
    if n >= 4:  # BUG-6a：按累计计数判终审，驳回重走未清零 → 只重批初审也被当成全批完
        conn.execute("UPDATE approval_board SET stage='approved' WHERE doc_id=?", (doc_id,))
    conn.commit()
    return n


def reject_doc(conn, doc_id, actor):
    _board(conn, doc_id)
    conn.execute("INSERT INTO approvals(doc_type,doc_id,segment,action,actor,ts) VALUES(?,?,?,?,?,?)",
                 ("sub_order", doc_id, 1, "reject", actor, NOW()))
    conn.execute("UPDATE approval_board SET stage='rejected' WHERE doc_id=?", (doc_id,))
    conn.commit()  # BUG-6b：驳回时未清 approved_segments，重走时计数继续累加


def void_doc(conn, doc_id, actor):
    conn.execute("INSERT INTO approvals(doc_type,doc_id,segment,action,actor,ts) VALUES(?,?,?,?,?,?)",
                 ("sub_order", doc_id, 0, "void", actor, NOW()))
    conn.commit()  # BUG-6c：作废只是记一条流水，不影响后续审批判定


def board_stage(conn, doc_id):
    return _board(conn, doc_id)["stage"]  # BUG-6d：看板是投影，与实际审批流水可能不同步
