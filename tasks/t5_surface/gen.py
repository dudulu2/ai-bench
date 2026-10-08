"""T5 连续几何建模参数生成器（可参数化）。

用法: python gen.py [--seed N]
输出: instance/seed-NNN.json（下发）与 instance/seed-NNN.truth.json（判分用）
"""
import argparse, json, os, random

HERE = os.path.dirname(os.path.abspath(__file__))

SPECIES = [
    {"key": "anemone", "zh": "银莲花", "petal_range": [5, 8], "leaf_range": [9, 15], "height_range": [80, 120]},
    {"key": "fern", "zh": "蕨类", "petal_range": [0, 0], "leaf_range": [12, 24], "height_range": [60, 110]},
    {"key": "lily", "zh": "百合", "petal_range": [6, 6], "leaf_range": [10, 18], "height_range": [90, 140]},
    {"key": "hosta", "zh": "玉簪", "petal_range": [6, 7], "leaf_range": [8, 14], "height_range": [50, 90]},
]

GOLDEN_ANGLE = 137.507764


# seed 1 为文档化基准实例，与 TASK.md 中写明的参数一致，不得漂移
PINNED_SEED1 = (
    {
        "species": "anemone",
        "species_zh": "银莲花",
        "stem_height_range": [90, 110],
        "leaf_count": 13,
        "petal_count": 6,
        "phyllotaxis": "alternate_spiral",
        "target_divergence_deg": round(GOLDEN_ANGLE, 3),
        "tolerance_deg": 8.0,
        "flower": True,
        "veins_required": True,
        "triangle_range": [20000, 200000],
    },
    {
        "golden_angle": GOLDEN_ANGLE,
        "tol_deg": 8.0,
        "leaf_count": 13,
        "petal_count": 6,
        "angle_series_len": 12,
        "internode_len": 13,
        "triangle_range": [20000, 200000],
        "expect_monotonic_gradient": True,
        "topology_limits": {
            "non_manifold_edges": 0,
            "degenerate_triangles": 0,
            "flipped_normals_ratio_max": 0.01,
        },
        "manifest_tolerance": 0.10,
    },
)


def build(seed: int):
    if seed == 1:
        return json.loads(json.dumps(PINNED_SEED1[0])), json.loads(json.dumps(PINNED_SEED1[1]))
    rng = random.Random(seed)
    sp = rng.choice(SPECIES)
    leaf_count = rng.randint(*sp["leaf_range"])
    petal = rng.randint(*sp["petal_range"]) if sp["petal_range"][1] else 0
    hmin, hmax = sp["height_range"]
    params = {
        "species": sp["key"],
        "species_zh": sp["zh"],
        "stem_height_range": [hmin, hmax],
        "leaf_count": leaf_count,
        "petal_count": petal,
        "phyllotaxis": "alternate_spiral",
        "target_divergence_deg": round(GOLDEN_ANGLE, 3),
        "tolerance_deg": 8.0,
        "flower": petal > 0,
        "veins_required": True,
        "triangle_range": [20000, 200000],
    }
    truth = {
        "golden_angle": GOLDEN_ANGLE,
        "tol_deg": 8.0,
        "leaf_count": leaf_count,
        "petal_count": petal,
        "angle_series_len": leaf_count - 1,
        "internode_len": leaf_count,
        "triangle_range": [20000, 200000],
        "expect_monotonic_gradient": True,
        "topology_limits": {
            "non_manifold_edges": 0,
            "degenerate_triangles": 0,
            "flipped_normals_ratio_max": 0.01,
        },
        "manifest_tolerance": 0.10,
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
    print(f"wrote instance/seed-{a.seed:03d}.json  species={params['species']} leaves={params['leaf_count']}")


if __name__ == "__main__":
    main()
