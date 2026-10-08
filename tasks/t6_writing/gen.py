"""T6 文笔题参数生成器（可参数化）。

用法: python gen.py [--seed N]
输出: instance/seed-NNN.json（下发）与 instance/seed-NNN.truth.json（判分用）
"""
import argparse, json, os, random

HERE = os.path.dirname(os.path.abspath(__file__))

BASES = [
    {
        "key": "little_red_riding_hood",
        "zh": "小红帽",
        "chars": ["小红帽", "外婆", "狼", "猎人"],
        "card": {
            "小红帽": "住在村庄与森林交界处的少女，总是穿着红色斗篷",
            "外婆": "小红帽的外婆，住在森林的另一边",
            "狼": "会说话的大灰狼，住在森林里",
            "猎人": "住在村庄里的成年男子，擅长使用枪",
        },
        "banned": [
            "狼吃掉外婆后被猎人剖腹救出",
            "狼假扮外婆躺在床上",
            "从此以后他们幸福地生活在一起",
        ],
    },
    {
        "key": "three_little_pigs",
        "zh": "三只小猪",
        "chars": ["猪老大", "猪老二", "猪老三", "狼"],
        "card": {
            "猪老大": "用稻草盖房的大哥",
            "猪老二": "用木头盖房的二哥",
            "猪老三": "用砖头盖房的三弟",
            "狼": "会吹气的大灰狼",
        },
        "banned": ["狼吹倒草房和木房", "狼从烟囱爬进去", "从此以后他们幸福地生活在一起"],
    },
]

TONES = ["反套路 + 全龄向", "冷峻写实", "荒诞幽默"]


# seed 1 为文档化基准实例，与 TASK.md 中写明的参数一致，不得漂移
PINNED_SEED1 = (
    {
        "base_key": "little_red_riding_hood",
        "base_zh": "小红帽",
        "tone": "反套路 + 全龄向",
        "word_range": [800, 1600],
        "characters": BASES[0]["card"],
        "rules": [
            "基础人设必须保留准确，不可以违背",
            "情节不得与原始故事相同",
            "可添加配角，但配角戏份不得超过戏份最少的主角",
            "有伏笔必须回收",
            "允许反常规，但必须有逻辑",
            "所有主角必须出现且有戏份",
        ],
        "banned_plots": BASES[0]["banned"],
    },
    {
        "required_chars": ["小红帽", "外婆", "狼", "猎人"],
        "word_min": 800,
        "word_max": 1600,
        "banned_ngrams": BASES[0]["banned"],
        "banned_patterns": [r"从此.{0,12}(幸福|快乐)", r"圆满结局"],
    },
)


def build(seed: int):
    if seed == 1:
        return json.loads(json.dumps(PINNED_SEED1[0])), json.loads(json.dumps(PINNED_SEED1[1]))
    rng = random.Random(seed)
    base = rng.choice(BASES)
    lo, hi = rng.choice([(800, 1600), (1200, 2000), (600, 1200)])
    params = {
        "base_key": base["key"],
        "base_zh": base["zh"],
        "tone": rng.choice(TONES),
        "word_range": [lo, hi],
        "characters": base["card"],
        "rules": [
            "基础人设必须保留准确，不可以违背",
            "情节不得与原始故事相同",
            "可添加配角，但配角戏份不得超过戏份最少的主角",
            "有伏笔必须回收",
            "允许反常规，但必须有逻辑",
            "所有主角必须出现且有戏份",
        ],
        "banned_plots": base["banned"],
    }
    truth = {
        "required_chars": list(base["card"].keys()),
        "word_min": lo,
        "word_max": hi,
        "banned_ngrams": base["banned"],
        "banned_patterns": [r"从此.{0,12}(幸福|快乐)", r"圆满结局"],
    }
    return params, truth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    params, truth = build(a.seed)
    out = os.path.join(HERE, "instance")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, f"seed-{a.seed:03d}.json"), "w", encoding="utf-8") as f:
        json.dump({"seed": a.seed, **params}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out, f"seed-{a.seed:03d}.truth.json"), "w", encoding="utf-8") as f:
        json.dump(truth, f, ensure_ascii=False, indent=2)
    print(f"wrote instance/seed-{a.seed:03d}.json  base={params['base_zh']} words={params['word_range']}")


if __name__ == "__main__":
    main()
