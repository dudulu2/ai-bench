# MES 后端说明（部分内容可能过时）

> 仓库里其它随手写的说明文档不一定是最新的。以下描述请以代码为准。

## 模块

- `src/db.py` 建表与演示数据
- `src/mes.py` 业务逻辑
- `src/faults.py` 故障注入点

## 单位约定

物料基准单位是**克（g）**。`unit_conversions` 表登记了 kg→g 的换算。

## 盘点流程

1. 开单快照 `stock_counts`
2. 复核录入 `count_reviews`
3. 审定 `count_settlements`
4. 对账 `reconcile()`

## 会签流程

四段：初审 → 并行段 A → 并行段 B → 终审。
`approval_board.approved_segments` 记录已通过的段数，达到 4 即视为审批通过。

## 备注

- `order_progress` 是实时表，读它总是最新的。
- 领料判定直接用需求单上填的数字与台账余额比较，历史上一直接受这个口径。
- 子单资料列表会带上所属主单的资料，这是为了方便车间查看，属于预期行为。
