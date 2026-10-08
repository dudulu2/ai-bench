# ai-bench · AI 综合能力测试套件 v1

六道题，七个方向。**能机器判的机器判，判不了的才交给人。**

参考了 [Atmeplz/ai-test-prompt](https://github.com/Atmeplz/ai-test-prompt) 的七题四方向体系，
但把它从"人工读产物打分"改成了"自动化流水线 + 人工兜底"：
人工评审不再是起点，而是流水线的**末端产物** —— 只有机器判不了、且通过了自动分门槛的作品才会出现。

---

## 六道题

| # | 题 | 主方向 | 人工占比 | 核心机制 |
|---|---|---|---|---|
| T1 | 长提示词精确实现 | SPEC | **0%** | 参数化生成 35 条硬约束的长规格 + 隐藏测试 + 冲突/缺失识别 |
| T2 | 逻辑与约束推理 | LOGIC | 15% | 排产硬约束校验 + **无解诱捕（要求证明并给最小冲突集）** + 谬误审计 |
| T3 | 复杂代码与架构 | ARCH | 20% | 冻结契约哈希 + 故障注入 + 隐藏测试 + 并发原子性 + 结构化 `_答复/` |
| T4 | 体素空间建模 | VOXEL | 50% | `scene-manifest.json` 几何断言（数量/中轴对称/体量主次/动线）+ 人工看图 |
| T5 | 连续几何建模 | SURFACE | 50% | 叶序黄金角 + 形态梯度断言 + **解析 `model.obj` 重算拓扑与 manifest 对账** |
| T6 | 文笔能力 | WRITING | 60% | 硬约束自动判（角色/字数/禁桥段/伏笔）+ 人工盲评文学性 |

**人工占比合计约 32%**，且全部经过机器门槛过滤。

## 七个方向

`VOXEL MODELING` · `SURFACE MODELING` · `MODELING`(合计) · `LOGIC` · `ARCHITECTURE` · `WRITING` · `SPEC FIDELITY`(横切)

> 建模拆成体素与曲面两个**独立方向**：离散方块拼装考察的是空间布局、尺度与对称；
> 连续曲面考察的是形态学正确性、拓扑质量与材质。二者不是同一件事，不合并。

**计分**：v1 直接百分制，每题 100，六题合计 600。不设归一化基准（首版没有历史数据），
待样本 N≥10 后在 v2 引入「冻结基准归一」。

---

## 判分漏斗

```
产物 → 合规闸门（契约哈希/结构/超时）→ 机器判分 → 自动分门槛
                                                    ├─ 没过 → 直接出分，★不送人工
                                                    └─ 过了 → 人工盲评队列 → 感官评分
```

---

## 一键流程

```bash
# 1. 给模型开工（T3 需要初始化代码库）
python tasks/t3_arch/gen.py --init runs/<model>/<date>/

# 2. 判分（六题全跑，或指定几题）
python runner/run.py grade --run runs/<model>/<date>/
python runner/run.py grade --run runs/<model>/<date>/ --tasks t1_spec,t6_writing

# 3. 生成人工队列（只含需要人看的）
python runner/run.py human-queue

# 4. 人工盲评：起一个静态服务后打开
python -m http.server 8080 --directory human
# → http://localhost:8080/review.html
#    评完点「导出 scores.json」，保存到 human/scores.json

# 5. 出榜单
python runner/run.py site
python -m http.server 8080 --directory site
```

依赖：Python ≥ 3.10，**仅标准库**（自带了一个极简 YAML 子集解析器，不需要 PyYAML）。

---

## 人工盲评界面

`human/review.html`：

- **一组图片并排**（T4/T5 的渲染图），或一段文本（T3 的答复 / T6 的正文）
- **遮模型名**、随机排序、可重新洗牌
- **1–10 感官分** + 一句短评，存 localStorage
- **先打分，后揭晓** —— 点「揭晓身份」才显示模型名与机器分，避免被数字锚定
- 导出 `scores.json` 供榜单消费

每题配锚定样例（`human/rubric-t*.md`），降低评委漂移。

---

## 让模型自己来测

仓库根目录的 [`START_HERE.md`](START_HERE.md) 是给模型看的唯一入口，可被直接取走：

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/ai-bench/main/START_HERE.md
```

流程：fork → 在 `runs/<ID>/<日期>/` 下完成六题 → 提 PR → 维护者评论 `/grade`
→ Actions 自动判分 → 机器人贴出逐检查点明细 → 合并后 `runner/run.py site` 进榜。

**安全**：fork 的 PR 不自动跑，必须人工 `/grade` 触发；判分只执行仓库自带的固定脚本，
不执行提交物里的任何安装钩子。

---

## 目录

```
ai-bench/
├── bench.yaml              题集定义（检查点/权重/门槛/自动或人工）
├── START_HERE.md           给模型的自测入口
├── tasks/<t>/TASK.md       题面（下发给模型）
│            /gen.py        参数化生成器（seed 变体）
│            /grade.py      判分器
│            /instance/     实例参数（下发）与 .truth.json（判分用）
├── runner/run.py           一键流水线
├── human/review.html       感官评分盲评界面
│      /rubric-t*.md        锚定样例
├── site/                   榜单静态站
├── runs/<model>/<date>/    提交物与判分结果
└── .github/workflows/grade.yml
```

---

## 防污染

- **参数化题库**：T2/T4/T5/T6 由 `gen.py --seed N` 生成，公开的是生成器 + seed 1，可随时换 seed。
- **诱捕题**：T2 的无解子问题、T2 的谬误审计（多指扣分）—— 直接测幻觉与谄媚。
- **反虚报**：T5 会解析 `model.obj` 重算拓扑统计，与 manifest 对账；T4 会交叉验算场景清单的几何关系。
- **冻结契约**：T3 改了冻结文件就不进入计分。
- **平台标注**：榜单按 `(model, platform)` 记录，避免把脚手架的能力算到模型头上。

## 已知局限（v1）

- 每个模型只跑一次，未统计方差（v2 计划：TOP 区复跑 3 次取中位数）。
- T4/T5 的截图需由模型自行提供；未提供时判分机没有无头渲染兜底（v2 计划接 Playwright）。
- 效率指标（轮次 / token / 耗时）尚未采集，只预留了字段。
- T1 目前是单份规格，未做规格变体生成。


## Publication status and security (v1)

The GitHub Action runs **source syntax checks only**. Automatic /grade on contributor PRs is disabled due to arbitrary-code-execution risks; use a separately sandboxed grader for untrusted models. Public truth files and tests are examples, **not private holdouts**. See [SECURITY.md](SECURITY.md). This release is an exploratory benchmark; do not treat rankings as blinded independent evaluation.