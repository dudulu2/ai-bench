"""T4 体素场景参数生成器（可参数化）。

用法: python gen.py [--seed N]
输出: instance/seed-NNN.json（下发）与 instance/seed-NNN.truth.json（判分用）
"""
import argparse, json, os, random

HERE = os.path.dirname(os.path.abspath(__file__))

ROOFS_MAIN = ["wudian", "xieshan", "zanjian"]
TERRAIN = ["三级台地", "缓坡", "平地"]
TIME = ["黄昏", "清晨", "正午"]


# seed 1 为文档化基准实例，与 TASK.md 中写明的参数一致，不得漂移
PINNED_SEED1 = (
    {
        "buildings_total": 7,
        "main_roof": "wudian",
        "secondary_count": 4,
        "pagoda_levels": 7,
        "terrain": "三级台地",
        "terrace_levels": 3,
        "time_of_day": "黄昏",
        "axis_x": 0.0,
        "palette": {"wall": "#8E3B3B", "roof": "#2F5D62", "wood": "#7A4B2A"},
    },
    {
        "roles_required": ["main_hall", "secondary", "gate", "pagoda"],
        "secondary_count": 4,
        "pagoda_levels": 7,
        "main_roof": "wudian",
        "terrace_levels": 3,
        "voxel_count_range": [2000, 300000],
        "symmetry_tol": 0.51,
    },
)


def build(seed: int):
    if seed == 1:
        return json.loads(json.dumps(PINNED_SEED1[0])), json.loads(json.dumps(PINNED_SEED1[1]))
    rng = random.Random(seed)
    n_secondary = rng.choice([2, 4, 6])
    pagoda_levels = rng.choice([5, 7, 9])
    params = {
        "buildings_total": 1 + n_secondary + 1 + 1,
        "main_roof": rng.choice(ROOFS_MAIN),
        "secondary_count": n_secondary,
        "pagoda_levels": pagoda_levels,
        "terrain": rng.choice(TERRAIN),
        "terrace_levels": 3 if rng.random() < 0.6 else 1,
        "time_of_day": rng.choice(TIME),
        "axis_x": 0.0,
        "palette": {"wall": "#8E3B3B", "roof": rng.choice(["#2F5D62", "#3A4E48", "#5B3A29"]), "wood": "#7A4B2A"},
    }
    truth = {
        "roles_required": ["main_hall", "secondary", "gate", "pagoda"],
        "secondary_count": n_secondary,
        "pagoda_levels": pagoda_levels,
        "main_roof": params["main_roof"],
        "terrace_levels": params["terrace_levels"],
        "voxel_count_range": [2000, 300000],
        "symmetry_tol": 0.51,
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
    print(f"wrote instance/seed-{a.seed:03d}.json  buildings_total={params['buildings_total']}")


if __name__ == "__main__":
    main()
