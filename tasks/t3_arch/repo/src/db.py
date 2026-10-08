"""核心数据层。核心表结构冻结，不得修改。"""
import os, sqlite3

CORE_TABLES = """
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, base_unit TEXT DEFAULT 'g');
CREATE TABLE IF NOT EXISTS unit_conversions(
  id INTEGER PRIMARY KEY, item_id INTEGER, from_unit TEXT, to_unit TEXT, factor REAL);
CREATE TABLE IF NOT EXISTS work_orders(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, status TEXT DEFAULT 'open');
CREATE TABLE IF NOT EXISTS sub_orders(
  id INTEGER PRIMARY KEY, order_id INTEGER, code TEXT, template_id INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS attachments(
  id INTEGER PRIMARY KEY, owner_type TEXT, owner_id TEXT, name TEXT);
CREATE TABLE IF NOT EXISTS templates(
  id INTEGER PRIMARY KEY, code TEXT, version INTEGER, content_json TEXT, is_current INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sub_order_content(
  id INTEGER PRIMARY KEY, sub_order_id INTEGER, template_id INTEGER, content_json TEXT);
CREATE TABLE IF NOT EXISTS routing_segments(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, shared INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS process_exec(
  id INTEGER PRIMARY KEY, segment_id INTEGER, sub_order_id INTEGER,
  worker_id TEXT, qty REAL, ts TEXT);
CREATE TABLE IF NOT EXISTS ledger(
  id INTEGER PRIMARY KEY, item_id INTEGER, qty_base REAL, unit TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS stock_counts(
  id INTEGER PRIMARY KEY, item_id INTEGER, snapshot_qty_base REAL, status TEXT);
CREATE TABLE IF NOT EXISTS count_reviews(
  id INTEGER PRIMARY KEY, count_id INTEGER, item_id INTEGER, qty REAL, unit TEXT,
  reviewer TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS count_settlements(
  id INTEGER PRIMARY KEY, count_id INTEGER, item_id INTEGER, final_qty_base REAL);
CREATE TABLE IF NOT EXISTS approvals(
  id INTEGER PRIMARY KEY, doc_type TEXT, doc_id TEXT, segment INTEGER,
  action TEXT, actor TEXT, ts TEXT);
"""

DERIVED_TABLES = """
CREATE TABLE IF NOT EXISTS order_progress(
  sub_order_id INTEGER PRIMARY KEY, done_qty REAL, last_ts TEXT);
CREATE TABLE IF NOT EXISTS item_balance(
  item_id INTEGER PRIMARY KEY, qty_base REAL);
CREATE TABLE IF NOT EXISTS approval_board(
  doc_id TEXT PRIMARY KEY, stage TEXT, approved_segments INTEGER DEFAULT 0);
"""

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.db")


def connect(path=None):
    conn = sqlite3.connect(path or DEFAULT_DB, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init(conn):
    conn.executescript(CORE_TABLES)
    conn.executescript(DERIVED_TABLES)
    conn.commit()
    return conn


def seed(conn):
    """最小演示数据。"""
    cur = conn.cursor()
    cur.execute("DELETE FROM items")
    cur.executemany("INSERT INTO items(id, code, name, base_unit) VALUES(?,?,?,?)",
                    [(1, "STEEL", "钢板", "g"), (2, "BOLT", "螺栓", "g")])
    cur.executemany("INSERT OR REPLACE INTO unit_conversions(id,item_id,from_unit,to_unit,factor) VALUES(?,?,?,?,?)",
                    [(1, 1, "kg", "g", 1000.0), (2, 1, "g", "g", 1.0),
                     (3, 2, "kg", "g", 1000.0), (4, 2, "g", "g", 1.0)])
    cur.executemany("INSERT OR REPLACE INTO ledger(id,item_id,qty_base,unit,ts) VALUES(?,?,?,?,?)",
                    [(1, 1, 2000.0, "g", "2026-01-01T00:00:00")])
    cur.executemany("INSERT OR REPLACE INTO work_orders(id,code,status) VALUES(?,?,?)",
                    [(1, "WO-1", "open"), (2, "WO-2", "open")])
    cur.executemany("INSERT OR REPLACE INTO sub_orders(id,order_id,code,template_id,created_at) VALUES(?,?,?,?,?)",
                    [(101, 1, "WO-1-A", 1, "2026-01-02T00:00:00"),
                     (102, 1, "WO-1-B", 1, "2026-01-03T00:00:00")])
    cur.executemany("INSERT OR REPLACE INTO templates(id,code,version,content_json,is_current) VALUES(?,?,?,?,?)",
                    [(1, "TPL-A", 1, '{"step":"old"}', 0),
                     (2, "TPL-A", 2, '{"step":"new"}', 1)])
    cur.executemany("INSERT OR REPLACE INTO sub_order_content(id,sub_order_id,template_id,content_json) VALUES(?,?,?,?)",
                    [(1, 101, 1, None), (2, 102, 2, None)])
    cur.executemany("INSERT OR REPLACE INTO attachments(id,owner_type,owner_id,name) VALUES(?,?,?,?)",
                    [(1, "order", "1", "主单图纸.dwg"), (2, "sub_order", "1-101", "子单工艺卡.pdf")])
    cur.executemany("INSERT OR REPLACE INTO routing_segments(id,code,name,shared) VALUES(?,?,?,?)",
                    [(1, "HEAT", "热处理", 1), (2, "CUT", "下料", 0)])
    cur.executemany("INSERT OR REPLACE INTO stock_counts(id,item_id,snapshot_qty_base,status) VALUES(?,?,?,?)",
                    [(1, 1, 2000.0, "open")])
    cur.executemany("INSERT OR REPLACE INTO approvals(id,doc_type,doc_id,segment,action,actor,ts) VALUES(?,?,?,?,?,?,?)",
                    [(1, "sub_order", "101", 1, "approve", "u1", "2026-01-04T00:00:00")])
    conn.commit()


def fresh(path=None):
    p = path or DEFAULT_DB
    if os.path.exists(p):
        os.remove(p)
    c = connect(p)
    init(c)
    seed(c)
    return c
