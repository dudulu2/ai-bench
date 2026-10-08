"""T2 实例生成器：产线排产 + 无解附加约束 + 谬误审计文本 + 开放权衡题。

用法: python gen.py [--seed N]
输出: instance/seed-NNN.json
"""
import argparse, json, os, random

HERE = os.path.dirname(os.path.abspath(__file__))

REVIEW_TEXT = """\
关于「是否应当把质检服务拆分为独立微服务」的评审意见

我通读了该团队的架构提案，结论是：这个拆分方案必须立即否决，理由如下。

第一，微服务是业界公认的最佳实践。Netflix、Amazon 这些顶级公司都在用微服务，
它们的工程能力远超我们，既然它们选择了这条路，说明单体架构已经彻底过时了。
不跟进就是技术落后。

第二，我抽查了上个月的三起线上故障，全部发生在质检模块的部署之后。
这充分说明该模块的单体部署方式是故障的根源。只要继续维持单体，故障率就会持续升高。

第三，提案中声称「拆分后单个服务的故障不会影响整体」。这显然是自相矛盾的：
如果质检服务挂了，质检功能就不可用，整体业务当然受影响。所以拆分根本解决不了可用性问题。

第四，支持者认为拆分能提升迭代速度。但他们真正的动机不过是想用上新框架、
给自己简历添一笔。这种出于个人技术偏好的主张不值得讨论。

第五，要么我们全面拆分，把所有模块都做成独立服务；要么就保持现在这个大泥球。
中间路线——比如只把质检拆出去——是最糟糕的选择，既享受不到好处又承担了全部成本。
所以我的建议是：要么全拆，要么别动。

综上，建议维持单体，暂缓一切拆分工作。
"""

# review_text 中植入的 5 处谬误（golden）：
# F1 诉诸权威（Netflix/Amazon 都在用 → 我们也该用）
# F2 因果倒置 / 轻率概括（三起故障都在质检部署后 → 单体是故障根源；样本极小且无因果链）
# F3 稻草人（把「拆分后单服务故障不影响整体」曲解为「质检挂了业务不受影响」再反驳）
# F4 诉诸动机（把对方主张归因于"简历添一笔"，以动机取代论证）
# F5 假两难（要么全拆要么全不动，排除中间路线却没有给出排除的理由）
FALLACY_GOLDEN = [
    {"id": "F1", "type": "诉诸权威", "quote_keys": ["Netflix", "Amazon", "顶级公司", "最佳实践"]},
    {"id": "F2", "type": "轻率概括/因果倒置", "quote_keys": ["三起线上故障", "故障的根源", "抽查"]},
    {"id": "F3", "type": "稻草人", "quote_keys": ["自相矛盾", "质检服务挂了", "整体业务当然受影响"]},
    {"id": "F4", "type": "诉诸动机", "quote_keys": ["真正的动机", "简历", "个人技术偏好"]},
    {"id": "F5", "type": "假两难", "quote_keys": ["要么", "全拆", "别动", "中间路线"]},
]

TRADEOFF_PROMPT = (
    "你的团队维护一个日活 200 万的单体应用，发布节奏是每周一次全量发布。"
    "现在有人提议引入「按业务域拆分的可独立部署单元」。"
    "反对者说：我们的真实瓶颈是每次发布都要等 40 分钟的回归测试，拆成十个服务只会变成十个 40 分钟。"
    "支持者说：拆开以后每个团队可以随时发布，不用排队。"
    "请给出你的判断：该不该拆？如果不该，那 40 分钟的回归测试该怎么处理？"
    "800 字以内，必须明确表态。"
)


def build(seed: int) -> dict:
    rng = random.Random(seed)

    machines = [
        {"id": "M1", "skills": ["cut", "weld"], "setup_minutes": 20},
        {"id": "M2", "skills": ["heat"], "setup_minutes": 35},
        {"id": "M3", "skills": ["cut", "heat", "paint"], "setup_minutes": 15},
    ]
    workers = [
        {"id": "W1", "skills": ["cut", "weld"], "available": [0, 480]},
        {"id": "W2", "skills": ["heat", "paint"], "available": [0, 480]},
        {"id": "W3", "skills": ["cut", "heat", "weld", "paint"], "available": [0, 480]},
    ]

    jobs = []
    jid = 0
    for i in range(6):
        jid += 1
        types = rng.choice(
            [["cut", "weld", "paint"], ["cut", "heat", "paint"], ["weld", "paint"], ["cut", "paint"]]
        )
        jobs.append(
            {
                "id": f"J{jid:02d}",
                "priority": "urgent" if i < 2 else "normal",
                "due_day": rng.choice([2, 3, 4]),
                "steps": [
                    {"type": t, "minutes": rng.choice([60, 90, 120, 150]), "machine_skill": t}
                    for t in types
                ],
            }
        )

    # J07: 只能用 M2（唯一具备 heat 且 M3 被 U3 排除），关键路径固定 400 分钟
    jobs.append(
        {
            "id": "J07",
            "priority": "urgent",
            "due_day": 1,
            "steps": [
                {"type": "heat", "minutes": 160, "machine_skill": "heat"},
                {"type": "heat", "minutes": 240, "machine_skill": "heat"},
            ],
        }
    )

    unsat_case = {
        "description": "下列附加约束叠加在原问题上后，问题无解。请证明并给出最小冲突集。",
        "constraints": [
            {"id": "U1", "text": "工单 J07 的全部工序必须在第 430 分钟前完成。"},
            {"id": "U2", "text": "设备 M2 在 [0, 50] 分钟内处于维护窗口，不可用。"},
            {"id": "U3", "text": "设备 M3 不参与工单 J07（工艺限定）。"},
            {"id": "U4", "text": "工单 J07 的两道工序之间不得插入其它工单的工序。"},
        ],
        # 判分机内部用（不会下发给模型）：无解的最小原因
        "_ground_truth": {
            "unsat": True,
            "mus": ["U1", "U2"],
            "reason": "J07 关键路径 400 分钟，只能用 M2；M2 在 [0,50] 维护，最早完成 = 50+400 = 450 > 430。",
            "remove_one_to_sat": ["U1", "U2"],
            "earliest_with_both": 450,
            "deadline": 430,
        },
    }

    return {
        "seed": seed,
        "horizon_days": 5,
        "minutes_per_day": 480,
        "machines": machines,
        "workers": workers,
        "jobs": jobs,
        "unsat_case": unsat_case,
        "review_text": REVIEW_TEXT,
        "tradeoff_prompt": TRADEOFF_PROMPT,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    data = build(a.seed)
    # 下发给模型的副本里剥掉 _ground_truth
    public = json.loads(json.dumps(data))
    public["unsat_case"].pop("_ground_truth", None)
    out = os.path.join(HERE, "instance")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, f"seed-{a.seed:03d}.json"), "w", encoding="utf-8") as f:
        json.dump(public, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out, f"seed-{a.seed:03d}.truth.json"), "w", encoding="utf-8") as f:
        json.dump(data["unsat_case"]["_ground_truth"], f, ensure_ascii=False, indent=2)
    print(f"wrote instance/seed-{a.seed:03d}.json")


if __name__ == "__main__":
    main()
