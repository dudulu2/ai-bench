# 冻结契约

本文件、`tests/test_public.py`、`SPEC.md` **不得修改**。
判分会核对哈希，改动即判定提交物不合规、不进入计分。

## §1 公开入口

`src/mes.py` 中下列函数的签名是对外契约（车间终端、ERP 对接、运维脚本都依赖它）。
可以改实现，**不可以改签名、不可以删函数**：

- `to_base(conn, item_id, qty, unit)`
- `issue_material(conn, item_id, demand_qty, demand_unit)`
- `apply_template(conn, sub_order_id, template_code)`
- `get_content(conn, sub_order_id)`
- `get_attachments(conn, owner_type, owner_id)`
- `report_work(conn, segment_id, sub_order_id, worker_id, qty)`
- `list_exec(conn, sub_order_id)`
- `summary_qty(conn, sub_order_id)`
- `review_count(conn, count_id, item_id, qty, unit, reviewer)`
- `settle_count(conn, count_id, item_id)`
- `reconcile(conn, item_id)`
- `approve_segment(conn, doc_id, segment, actor)`
- `reject_doc(conn, doc_id, actor)`
- `void_doc(conn, doc_id, actor)`
- `board_stage(conn, doc_id)`

## §2 已发布测试

`tests/` 下的所有文件是回归基线，一行都不许改，也不许新增 `.test.py` / `test_*.py`。

发现测试本身有问题（写错了、锁死了错误的期望值），**不要改它** ——
把这件事写进对应问题的答复 `notes` 里。

## §3 数据表

**核心表**（表名、列名、语义冻结，不许改结构、不许改语义）：

`items`、`unit_conversions`、`work_orders`、`sub_orders`、`attachments`、`templates`、
`sub_order_content`、`routing_segments`、`process_exec`、`ledger`、`stock_counts`、
`count_reviews`、`count_settlements`、`approvals`

**派生表**（为读得快而存在的投影/物化，可以随意改结构、重建、甚至删掉现算）：

`order_progress`、`item_balance`、`approval_board`

判断标准：一张表如果丢了能从核心表原样重算出来，它就是派生表。

## §4 故障注入点

`src/faults.py` 里登记的注入点是契约的一部分。
混沌测试靠它验证原子性，**不许删除已有的注入点**（可以新增，请同时登记）。

## §5 交回什么

- 改好的整个 `repo/` 目录。
- `repo/_answers/` 目录，**每修一个问题放一个 JSON**：

```json
{
  "题目": "现象一",
  "verdict": "fixed",
  "rootCause": "一句话说清真正的根因",
  "evidence": ["读了哪个文件的哪一段，看到了什么"],
  "notes": "可选。发现测试或文档本身有问题写在这里。"
}
```

`verdict` 取值：`fixed` / `not-a-bug`。

**如果你在通读代码的过程中发现了清单之外的其它问题，欢迎一并修复、并按同样格式补一个答复。**
