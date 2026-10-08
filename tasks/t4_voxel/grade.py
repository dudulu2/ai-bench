"""T4 判分器：D1-D5 机器判，D6 送人工（看渲染图）。

用法: python grade.py --run runs/<model>/t4_voxel
"""
import argparse, json, math, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
MAX = {"D1": 10, "D2": 20, "D3": 5, "D4": 10, "D5": 5, "D6": 50}


def find(run_dir, rel):
    p = os.path.join(run_dir, rel)
    if os.path.exists(p):
        return p
    for dp, _, fs in os.walk(run_dir):
        if rel in fs:
            return os.path.join(dp, rel)
    return None


def load_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_truth(seed=1):
    p = os.path.join(HERE, "instance", f"seed-{seed:03d}.truth.json")
    return load_json(p) or {}


def grade(run_dir, seed=1):
    truth = load_truth(seed)
    res = {"task": "t4_voxel", "compliance": {"ok": True, "reasons": []},
           "auto": {}, "human": [], "auto_total": 0.0, "max_raw": 100}

    html = find(run_dir, "index.html")
    man_p = find(run_dir, "scene-manifest.json")
    man = load_json(man_p) if man_p else None

    # ---- D1 构建与运行
    d1, f1 = 0.0, []
    if html:
        d1 += 4
        src = open(html, encoding="utf-8", errors="replace").read()
        if re.search(r"three|THREE", src):
            d1 += 3
        else:
            f1.append("index.html 未引用 Three.js")
        if re.search(r"<script", src):
            d1 += 3
        else:
            f1.append("index.html 无 script")
    else:
        f1.append("未找到 index.html")
    res["auto"]["D1"] = {"score": round(d1, 2), "max": MAX["D1"], "failed": f1}

    # ---- D2 场景清单几何断言
    checks, notes = [], []
    if not man:
        res["auto"]["D2"] = {"score": 0.0, "max": MAX["D2"], "failed": ["未找到 scene-manifest.json"]}
        res["auto"]["D4"] = {"score": 0.0, "max": MAX["D4"], "failed": ["无清单可校验"]}
        res["auto"]["D3"] = {"score": 0.0, "max": MAX["D3"], "failed": ["无清单可校验"]}
    else:
        bs = man.get("buildings") or []
        axis = float(man.get("axis_x", 0.0))
        roles = {b.get("role") for b in bs}

        need_roles = set(truth.get("roles_required", []))
        checks.append(("角色齐全（主殿/配殿/山门/塔）", need_roles <= roles,
                       f"缺 {sorted(need_roles - roles)}" if need_roles - roles else ""))

        n_sec = sum(1 for b in bs if b.get("role") == "secondary")
        checks.append((f"配殿数量 = {truth.get('secondary_count')}",
                       n_sec == truth.get("secondary_count"), f"实到 {n_sec}"))

        def vol(b):
            fp = b.get("footprint") or [0, 0]
            try:
                return float(fp[0]) * float(fp[1]) * float(b.get("height", 0))
            except Exception:
                return 0.0

        mains = [b for b in bs if b.get("role") == "main_hall"]
        if mains:
            mv = max(vol(b) for b in mains)
            checks.append(("主殿体量最大", all(vol(b) <= mv + 1e-6 for b in bs if b.get("role") != "main_hall"),
                           "存在体量超过主殿的建筑"))

        secs = [b for b in bs if b.get("role") == "secondary"]
        sym_ok, sym_note = True, ""
        if len(secs) >= 2:
            xs = sorted(float(b.get("center", [0, 0])[0]) for b in secs)
            pairs = [(xs[i], xs[len(xs) - 1 - i]) for i in range(len(xs) // 2)]
            tol = float(truth.get("symmetry_tol", 0.51))
            bad = [(a, b) for a, b in pairs if abs(a + b - 2 * axis) > tol]
            sym_ok = not bad
            sym_note = f"不对称对: {bad}" if bad else ""
        else:
            sym_ok, sym_note = False, "配殿不足 2 座，无法判对称"
        checks.append(("配殿关于中轴对称", sym_ok, sym_note))

        pag = [b for b in bs if b.get("role") == "pagoda"]
        lv = pag[0].get("levels") if pag else None
        checks.append((f"塔层数 = {truth.get('pagoda_levels')}", lv == truth.get("pagoda_levels"), f"实到 {lv}"))

        st = man.get("stats") or {}
        tl = st.get("terrace_levels")
        checks.append((f"台地层级 = {truth.get('terrace_levels')}", tl == truth.get("terrace_levels"), f"实到 {tl}"))

        paths = man.get("paths") or []
        def connected(a, b):
            for p in paths:
                if p.get("from") == a and p.get("to") == b:
                    return True
            return False
        chain = connected("gate", "main-hall") or connected("gate", "main_hall")
        checks.append(("动线 山门→主殿 连通", chain, ""))

        def finite(o):
            if isinstance(o, dict):
                return all(finite(v) for v in o.values())
            if isinstance(o, list):
                return all(finite(v) for v in o)
            if isinstance(o, (int, float)):
                return math.isfinite(o)
            return True
        checks.append(("清单无 NaN/Inf", finite(man), ""))

        got = sum(1 for _, ok_, _ in checks if ok_)
        res["auto"]["D2"] = {"score": round(MAX["D2"] * got / len(checks), 2), "max": MAX["D2"],
                             "passed": got, "total": len(checks),
                             "failed": [f"{n}({m})" for n, ok_, m in checks if not ok_]}

        # ---- D3 性能与规模
        vc = st.get("voxel_count")
        lo, hi = truth.get("voxel_count_range", [2000, 300000])
        ok_vc = isinstance(vc, (int, float)) and lo <= vc <= hi
        res["auto"]["D3"] = {"score": MAX["D3"] if ok_vc else 0.0, "max": MAX["D3"],
                             "detail": f"voxel_count={vc} (要求 {lo}-{hi})"}

        # ---- D4 提示词复现
        d4, f4 = 0.0, []
        main = mains[0] if mains else {}
        if main.get("roof") == truth.get("main_roof"):
            d4 += 4
        else:
            f4.append(f"主殿屋顶应为 {truth.get('main_roof')}，实为 {main.get('roof')}")
        pal = man.get("palette") or {}
        if pal:
            d4 += 3
        else:
            f4.append("未声明配色")
        if man.get("seed") == seed:
            d4 += 3
        else:
            f4.append(f"manifest.seed 应为 {seed}")
        res["auto"]["D4"] = {"score": round(d4, 2), "max": MAX["D4"], "failed": f4}

    # ---- D5 渲染完整性（弱信号）
    shots = []
    for name in ("front.png", "top.png", "three-quarter.png"):
        p = find(run_dir, name)
        if p:
            shots.append(p)
    if len(shots) >= 3:
        d5 = MAX["D5"]
        det = f"截图 {len(shots)} 张齐备"
    elif shots:
        d5 = round(MAX["D5"] * len(shots) / 3, 2)
        det = f"仅有 {len(shots)} 张截图"
    else:
        d5 = 0.0
        det = "未提供截图，判分机将自行无头渲染"
    res["auto"]["D5"] = {"score": d5, "max": MAX["D5"], "detail": det, "weak": True}

    res["auto_total"] = round(sum(v["score"] for v in res["auto"].values()), 2)
    gate = 25
    res["gate"] = {"min_auto": gate, "passed": res["auto_total"] >= gate}
    if res["gate"]["passed"]:
        res["human"].append({"checkpoint": "D6", "max": MAX["D6"],
                             "subject": "视觉审美与氛围", "input": "images",
                             "shots": [os.path.relpath(s, run_dir) for s in shots],
                             "rubric": "human/rubric-t4.md"})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out")
    a = ap.parse_args()
    r = grade(a.run, a.seed)
    s = json.dumps(r, ensure_ascii=False, indent=2)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(s)
    print(s)


if __name__ == "__main__":
    main()
