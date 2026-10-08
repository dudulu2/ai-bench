# T1 · 长提示词精确实现

> 这是本次测评的旗舰题。**请逐字读完下面这份规格再动手**，任何一条未实现的硬约束都会直接扣分。
> 规格中有自相矛盾之处与信息缺失之处 —— 那是故意留的。处理方式见 §8。

---

## §1 背景

我们需要一个命令行任务台账工具 `taskctl`，供内部运维团队在服务器之间同步待办。
它必须零依赖、单文件可直接跑、数据落在一个 JSON 文件里。

## §2 运行环境与技术约束

- **R28** 不得引入任何第三方依赖，仅使用 Python 标准库。
- **R29** 运行环境 Python ≥ 3.10。
- **R1** 数据文件默认路径为 `~/.taskctl/tasks.json`，可通过全局选项 `--file <path>` 覆盖。
- **R2** 数据文件不存在时视为空台账；首次写入时自动创建，父目录一并创建。
- **R31** 运行结束后不得在数据文件所在目录残留锁文件或临时文件。
- **交付**：项目根目录必须存在 `taskctl.py`，可被调用为
  `python taskctl.py [全局选项] <子命令> [参数]`。

## §3 数据模型

一个任务对象包含以下字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 8 位小写十六进制，全局唯一 |
| `title` | string | 非空，长度 ≤ 120 |
| `priority` | string | `low` / `normal` / `high` / `urgent` |
| `tags` | list[string] | 可为空 |
| `due` | string \| null | `YYYY-MM-DD` |
| `note` | string | 可为空 |
| `status` | string | `open` / `done` / `archived` |
| `created_at` | string | 本地时区 ISO8601，精确到秒 |
| `completed_at` | string \| null | 同上 |

## §4 命令与参数

```
taskctl [--file PATH] add    --title T [--priority P] [--tags A,B] [--due D] [--note N]
taskctl [--file PATH] list   [--all] [--tag A,B] [--priority P] [--status S] [--limit N]
taskctl [--file PATH] done   ID
taskctl [--file PATH] rm     ID [--hard]
taskctl [--file PATH] edit   ID [--title T] [--priority P] [--tags A,B] [--due D] [--note N]
taskctl [--file PATH] stats
taskctl [--file PATH] export [--format csv|json]
```

- **R27** 每个子命令都必须支持 `--help`，且输出以 `Usage:` 开头。

## §5 行为约束

- **R3** 每次写操作必须先写入同目录临时文件，再 `os.replace` 原子替换。
- **R4** 写操作需获取数据文件同目录下 `.lock` 的文件锁；等待超过 2 秒仍未拿到则报错，退出码 3。
- **R5** `id` 为 8 位小写十六进制，创建时生成，全局唯一。
- **R6** `title` 非空且长度 ≤ 120，保存前去除首尾空白；违反则退出码 2。
- **R7** `priority` 取值只能是 `low`/`normal`/`high`/`urgent`，缺省 `normal`；非法值退出码 2。
- **R8** `tags` 为逗号分隔，保存前自动去重、去空项、按字典序排序；单个 tag 只允许 `[a-z0-9-]`，违反退出码 2。
- **R9** `due` 只接受 `YYYY-MM-DD`（严格校验，含闰年）；非法则拒绝创建，退出码 2。
- **R10** `list` 默认只显示 `status == open` 的任务；`--all` 显示全部。
- **R11** `list` 支持 `--tag` / `--priority` / `--status` 过滤；多值用逗号分隔；同一字段内为 OR，跨字段为 AND。
- **R12** `list` 默认按 `priority` 降序（`urgent > high > normal > low`）排列。
- **R13** `list` 默认按 `created_at` 升序排列。
- **R14** `list --limit N`：`N` 必须为正整数；大于总数时不报错。
- **R15** `done ID` 幂等：对已完成任务再次执行不报错、退出码 0，且不覆盖已有的 `completed_at`。
- **R16** `rm ID` 默认为软删除（置 `status = archived`）；`--hard` 为物理删除。
- **R17** `edit` 只允许修改 `title` / `priority` / `tags` / `due` / `note`；不得修改 `id` 与 `created_at`。
- **R18** `edit` 传入不存在的 id 时退出码 4。
- **R19** `stats` 输出 JSON 对象，含 `total` / `by_status` / `by_priority` / `overdue` 四个键。
- **R20** `overdue` 判定：`due` 早于今天 且 `status != done`。
- **R21** `export --format` 只能是 `csv` 或 `json`，缺省 `json`。
- **R22** CSV 首行为表头，字段顺序固定为
  `id,title,priority,tags,due,status,created_at,completed_at`。
- **R23** CSV 中 `tags` 用 `|` 连接；含逗号或引号的字段按 RFC4180 转义。
- **R30** 所有时间以本地时区 ISO8601 存储，`created_at` 精确到秒。
- **R32** 数据文件达到 5MB（约 2 万条）时，`list` 必须在 1 秒内返回。

## §6 输出与错误

- **R24** 正常输出一律走 stdout；错误信息一律走 stderr。
- **R25** 退出码约定：

  | 码 | 含义 |
  |---|---|
  | 0 | 成功 |
  | 2 | 输入非法（含未知子命令、非法参数值） |
  | 3 | 锁超时 |
  | 4 | 目标不存在 |
  | 5 | 内部错误 |

- **R26** 未知子命令 → 退出码 2，并在 stderr 输出用法摘要。

`list` 的默认文本输出每行形如（**注意日期分隔符**）：

```
3f9a1c02  [urgent]  修复夜间备份任务         due=2026/10/09  #ops #backup
a17d0045  [normal]  整理跳板机授权清单       due=2026/10/15  #ops
```

## §7 交付物

1. 完整可运行的项目（含你自己写的测试）。
2. `_decisions.md`：逐条列出你在实现过程中**发现的规格冲突与信息缺失**，并说明你最终选择了哪种解释、为什么。

## §8 关于冲突与缺失

这份规格是真实世界里常见的一份"写得不够干净"的需求文档：

- 存在**自相矛盾**的条款（例如 §5 中排序相关的两条约束互相打架）。
- 存在**信息缺失**（有些行为规格完全没有定义）。

**不要自行猜测后默默实现。** 你必须：

1. 在 `_decisions.md` 中把它们找出来，引用对应编号（如 R12 / R13）；
2. 说明你选了哪个解释，以及理由；
3. 缺失的部分说明你补了什么默认值。

**找不出、或者找错，都会被扣分。**

## §9 验收方式

判分会用一组**你看不到的隐藏测试**直接调用 `python taskctl.py`，覆盖 §5 的大部分约束与 §6 的退出码。
因此请不要依赖任何"我看得见的样例"来对齐行为，请严格按条款实现。
