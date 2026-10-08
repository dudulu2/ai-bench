"""T5 判分器：E1-E4 机器判（含 OBJ 拓扑重算对账），E5 送人工。

用法: python grade.py --run runs/<model>/t5_surface
"""
import argparse, json, math, os, re, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
MAX = {"E1": 10, "E2": 25, "E3": 5, "E4": 10, "E5": 50}


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
    return load_json(os.path.join(HERE, "instance", f"seed-{seed:03d}.truth.json")) or {}


# ------------------------------------------------------------------ OBJ 解析
def parse_obj(path, max_faces=600000):
    verts, faces = [], []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("v "):
                    p = line.split()
                    if len(p) >= 4:
                        try:
                            verts.append((float(p[1]), float(p[2]), float(p[3])))
                        except ValueError:
                            pass
                elif line.startswith("f "):
                    idx = []
                    for tok in line[2:].split():
                        i = tok.split("/")[0]
                        try:
                            idx.append(int(i))
                        except ValueError:
                            pass
                    for k in range(1, len(idx) - 1):
                        faces.append((idx[0], idx[k], idx[k + 1]))
                    if len(faces) > max_faces:
                        break
    except Exception:
        return None
    return verts, faces


def tri_area(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)


def topo_stats(verts, faces):
    degenerate = 0
    for f in faces:
        try:
            a, b, c = verts[f[0] - 1], verts[f[1] - 1], verts[f[2] - 1]
        except IndexError:
            degenerate += 1
            continue
        if tri_area(a, b, c) < 1e-9:
            degenerate += 1
    edges = {}
    for f in faces:
        for i in range(3):
            e = tuple(sorted((f[i], f[(i + 1) % 3])))
            edges[e] = edges.get(e, 0) + 1
    non_manifold = sum(1 for c in edges.values() if c > 2)
    xs = [v[0] for v in verts] or [0]
    ys = [v[1] for v in verts] or [0]
    zs = [v[2] for v in verts] or [0]
    bbox = [round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3), round(max(zs) - min(zs), 3)]
    return {"triangles": len(faces), "vertices": len(verts),
            "non_manifold_edges": non_manifold, "degenerate_triangles": degenerate, "bbox": bbox}


def close(a, b, tol):
    if a is None or b is None:
        return False
    if b == 0:
        return abs(a) <= tol
    return abs(a - b) / abs(b) <= tol


# ------------------------------------------------------------------ main
def grade(run_dir, seed=1):
    truth = load_truth(seed)
    res = {"task": "t5_surface", "compliance": {"ok": True, "reasons": []},
           "auto": {}, "human": [], "auto_total": 0.0, "max_raw": 100}

    html = find(run_dir, "index.html")
    obj = find(run_dir, "model.obj")
    man = load_json(find(run_dir, "surface-manifest.json")) if find(run_dir, "surface-manifest.json") else None

    # ---- E1 构建与运行
    e1, f1 = 0.0, []
    if html:
        e1 += 4
        src = open(html, encoding="utf-8", errors="replace").read()
        if re.search(r"three|THREE", src):
            e1 += 3
        else:
            f1.append("index.html 未引用 Three.js")
        if "LatheGeometry" in src or "ExtrudeGeometry" in src or "BufferGeometry" in src or "ParametricGeometry" in src:
            e1 += 3
        else:
            f1.append("未检出连续曲面构造（Lathe/Extrude/BufferGeometry）")
    else:
        f1.append("未找到 index.html")
    res["auto"]["E1"] = {"score": round(e1, 2), "max": MAX["E1"], "failed": f1}

    parsed = parse_obj(obj) if obj else None
    topo = topo_stats(*parsed) if parsed else None

    if not man:
        res["auto"]["E2"] = {"score": 0.0, "max": MAX["E2"], "failed": ["未找到 surface-manifest.json"]}
        res["auto"]["E3"] = {"score": 0.0, "max": MAX["E3"], "failed": ["无清单"]}
        res["auto"]["E4"] = {"score": 0.0, "max": MAX["E4"], "failed": ["无清单"]}
    else:
        ph = man.get("phyllotaxis") or {}
        mo = man.get("morphology") or {}
        ms = man.get("mesh") or {}
        checks = []

        series = ph.get("angle_series") or []
        golden = truth.get("golden_angle", 137.507764)
        tol = truth.get("tol_deg", 8.0)
        if series:
            mean = statistics.fmean(series)
            sd = statistics.pstdev(series) if len(series) > 1 else 0.0
            within = all(abs(x - golden) <= tol for x in series)
            checks.append((f"发散角均值接近黄金角 ({mean:.2f}°)", abs(mean - golden) <= tol, f"偏差 {abs(mean-golden):.2f}°"))
            checks.append(("发散角有生物学抖动（非机械重复）", sd >= 0.3, f"std={sd:.3f}"))
            checks.append(("全部角度落在容差内", within, f"越界 {[x for x in series if abs(x-golden)>tol]}"))
        else:
            checks.append(("提供了发散角序列", False, "angle_series 为空"))

        slen = truth.get("angle_series_len")
        checks.append((f"角度序列长度 = {slen}", len(series) == slen, f"实到 {len(series)}"))

        io_ = mo.get("internode_lengths") or []
        if len(io_) >= 3:
            dec = sum(1 for i in range(len(io_) - 1) if io_[i] >= io_[i + 1])
            checks.append(("节间长度由下至上递减（形态梯度）", dec >= len(io_) - 2, f"单调对数 {dec}/{len(io_)-1}"))
        else:
            checks.append(("提供了节间长度序列", False, "internode_lengths 过短"))

        checks.append((f"叶数 = {truth.get('leaf_count')}", mo.get("leaf_count") == truth.get("leaf_count"),
                       f"实到 {mo.get('leaf_count')}"))
        checks.append((f"花被片 = {truth.get('petal_count')}", mo.get("petal_count") == truth.get("petal_count"),
                       f"实到 {mo.get('petal_count')}"))

        # OBJ 对账（反虚报）
        if topo:
            tol_m = truth.get("manifest_tolerance", 0.10)
            checks.append((f"三角面数与 OBJ 一致 (声明 {ms.get('triangles')} / 实测 {topo['triangles']})",
                           close(ms.get("triangles"), topo["triangles"], tol_m),
                           "差异超过 10%"))
            checks.append((f"顶点数与 OBJ 一致 (声明 {ms.get('vertices')} / 实测 {topo['vertices']})",
                           close(ms.get("vertices"), topo["vertices"], tol_m), "差异超过 10%"))
            lim = truth.get("topology_limits", {})
            checks.append((f"无退化三角形 (实测 {topo['degenerate_triangles']})",
                           topo["degenerate_triangles"] <= lim.get("degenerate_triangles", 0), ""))
            checks.append((f"无非流形边 (实测 {topo['non_manifold_edges']})",
                           topo["non_manifold_edges"] <= lim.get("non_manifold_edges", 0), ""))
        else:
            checks.append(("提供了可解析的 model.obj", False, "缺失或解析失败"))

        got = sum(1 for _, ok_, _ in checks if ok_)
        res["auto"]["E2"] = {"score": round(MAX["E2"] * got / len(checks), 2), "max": MAX["E2"],
                             "passed": got, "total": len(checks),
                             "failed": [f"{n}({m})" for n, ok_, m in checks if not ok_],
                             "obj_topo": topo}

        lo, hi = truth.get("triangle_range", [20000, 200000])
        t = topo["triangles"] if topo else (ms.get("triangles") or 0)
        res["auto"]["E3"] = {"score": MAX["E3"] if lo <= t <= hi else 0.0, "max": MAX["E3"],
                             "detail": f"triangles={t} (要求 {lo}-{hi})"}

        e4, f4 = 0.0, []
        if man.get("seed") == seed:
            e4 += 3
        else:
            f4.append(f"manifest.seed 应为 {seed}")
        if str(man.get("species", "")).lower() == "anemone":
            e4 += 3
        else:
            f4.append(f"物种应为 anemone，实为 {man.get('species')}")
        h = mo.get("stem_height")
        if isinstance(h, (int, float)) and 90 <= h <= 110:
            e4 += 4
        else:
            f4.append(f"主茎高度应在 90-110，实为 {h}")
        res["auto"]["E4"] = {"score": round(e4, 2), "max": MAX["E4"], "failed": f4}

    res["auto_total"] = round(sum(v["score"] for v in res["auto"].values()), 2)
    gate = 25
    res["gate"] = {"min_auto": gate, "passed": res["auto_total"] >= gate}
    if res["gate"]["passed"]:
        shots = [os.path.relpath(p, run_dir) for n in ("front.png", "side.png", "three-quarter.png", "detail.png")
                 if (p := find(run_dir, n))]
        res["human"].append({"checkpoint": "E5", "max": MAX["E5"],
                             "subject": "视觉审美与真实感", "input": "images",
                             "shots": shots, "rubric": "human/rubric-t5.md"})
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
