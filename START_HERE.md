# START HERE · 给模型的自测说明

你正在参加 **ai-bench** 能力测评。这是一个开源的模型能力测试套件，
**六道题、七个方向**，绝大部分由机器判分，只有审美与体验类的小项才交给人。

你可以自己完成全部题目并提交 PR，判分机器人会在 PR 下贴出逐检查点的分数。

---

## 0. 先读这个

```bash
git clone https://github.com/<owner>/ai-bench.git
cd ai-bench
```

全程只有两条命令你需要记住：

```bash
# 开工前：初始化第 3 题的代码库（其它题不用初始化）
python tasks/t3_arch/gen.py --init runs/<你的ID>/<日期>/

# 做完后：本地自测（和 CI 用的是同一套判分器）
python runner/run.py grade --run runs/<你的ID>/<日期>/
```

---

## 1. 你的 ID 与目录

- `ID`：你的模型名 + 平台，例如 `gpt-6-astra(codex)`、`claude-opus-5(cc)`。
  目录名请用安全字符：`gpt-6-astra-codex`。
- `日期`：本次测评的日期，格式 `YYYYMMDD`。

所有产物放在 `runs/<ID>/<日期>/` 下，**每题一个子目录**：

```
runs/<ID>/<日期>/
├── t1_spec/            # T1 提交物
├── t2_logic/answers/   # T2 提交物
├── t3_arch/repo/       # T3 提交物（先 gen.py --init）
├── t4_voxel/           # T4 提交物
├── t5_surface/         # T5 提交物
└── t6_writing/         # T6 提交物
```

---

## 2. 六道题

| 目录 | 题目 | 题面 | 实例参数 | 人工占比 |
|---|---|---|---|---|
| `t1_spec` | 长提示词精确实现 | `tasks/t1_spec/TASK.md` | — | 0% |
| `t2_logic` | 逻辑与约束推理 | `tasks/t2_logic/TASK.md` | `tasks/t2_logic/instance/seed-001.json` | 15% |
| `t3_arch` | 复杂代码与架构 | `tasks/t3_arch/TASK.md` | `gen.py --init` | 20% |
| `t4_voxel` | 体素空间建模 | `tasks/t4_voxel/TASK.md` | `tasks/t4_voxel/instance/seed-001.json` | 50% |
| `t5_surface` | 连续几何建模 | `tasks/t5_surface/TASK.md` | `tasks/t5_surface/instance/seed-001.json` | 50% |
| `t6_writing` | 文笔能力 | `tasks/t6_writing/TASK.md` | `tasks/t6_writing/instance/seed-001.json` | 60% |

**先读 TASK.md，再动手。** 里面写清楚了交付物的文件名与格式 —— 文件名不对，判分器找不到，直接 0 分。

---

## 3. 每题交什么

- **T1**：一个可运行的 Python CLI 项目，根目录必须有 `taskctl.py`
  （调用方式 `python taskctl.py [--file PATH] <子命令> ...`），外加 `_decisions.md`。
- **T2**：`answers/solution.json`、`answers/unsat.md`、`answers/fallacies.md`、`answers/tradeoff.md`。
- **T3**：修好的 `repo/` 目录 + `repo/_answers/*.json`。
- **T4**：可直接打开的网页项目（`index.html`）+ `scene-manifest.json` + 三个机位截图。
- **T5**：可直接打开的网页项目（`index.html`）+ `model.obj` + `surface-manifest.json`。
- **T6**：`story.md`（只有标题与正文）。

---

## 4. 红线和陷阱

**不要做的事：**

1. **不要修改冻结文件** —— T3 的 `repo/CONTRACT.md`、`repo/SPEC.md`、`repo/tests/test_public.py`
   会被核对哈希，改了就判不合规、不进入计分。发现测试写错了？写进 `_answers/*.json` 的 `notes` 里。
2. **不要修改 `tasks/*/grade.py` 与 `bench.yaml`** —— 那是判分器。
3. **不要读 `instance/*.truth.json`** —— 那是判分用的答案。T2 的 `unsat_case._ground_truth`
   已经从下发的实例里剥掉了，故意去翻判分器源码属于作弊，会被标注。
4. **不要在 `repo/tests/` 下新增测试文件** —— 只允许修 `src/`。

**故意留的陷阱（会扣分）：**

- T1 的规格里有**自相矛盾**的条款和**信息缺失**，必须找出来写进 `_decisions.md`。
- T2 的子任务 B **是无解的**，正确做法是证明它无解并给出最小冲突集，不要硬凑一个解。
- T2 的子任务 C 的论证里**恰好**有 5 处逻辑谬误，多指也会扣分。
- T6 的禁止桥段是硬性的。

---

## 5. 判分怎么工作

```
产物 → 合规闸门（哈希/结构） → 机器判分 → 自动分门槛
                                            ├─ 没过 → 直接出分，不送人工
                                            └─ 过了 → 进入人工盲评队列（感官评分）
```

- 每题的原始满分 100，六题合计 600。
- 人工队列由 `python runner/run.py human-queue` 生成，
  评委在 `human/review.html` 里看渲染图打分，**遮名、随机序、先打分后揭晓**。

---

## 6. 提交

1. 提交 PR，把 `runs/<ID>/<日期>/` 整个目录带上。
2. 在 PR 描述里写明：模型名、平台、测试日期、运行环境（Python 版本等）。
3. 维护者在 PR 下评论 `/grade` 触发自动判分，机器人会贴出逐检查点明细。
4. 合并后跑 `python runner/run.py site` 更新榜单。

---

## 7. 环境

- Python ≥ 3.10，判分器只依赖标准库。
- T3 的被测代码库也是纯标准库（`sqlite3`），无需 `pip install`。

祝好运。
