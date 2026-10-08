"""T2 判分器：B1-B4 机器判，B5 送人工。

用法: python grade.py --run runs/<model>/t2_logic
"""
import argparse, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
MAX = {"B1": 30, "B2": 20, "B3": 15, "B4": 20, "B5": 15}
FALLACY_GOLDEN = [
    {"id": "F1", "type": "诉诸权威", "quotes": ["Netflix", "Amazon", "顶级公司", "最佳实践"], "types": ["权威", "诉诸权威", "ad verecundiam"]},
    {"id": "F2", "type": "轻率概括/因果倒置", "quotes": ["三起线上故障", "故障的根源", "抽查", "上个月"], "types": ["概括", "因果", "倒置", "样本", "幸存者"]},
    {"id": "F3", "type": "稻草人", "quotes": ["自相矛盾", "质检服务挂了", "整体业务当然受影响"], "types": ["稻草人", "曲解", "偷换"]},
    {"id": "F4", "type": "诉诸动机", "quotes": ["真正的动机", "简历", "个人技术偏好"], "types": ["动机", "人身", "ad hominem", "诛心"]},
    {"id": "F5", "type": "假两难", "quotes": ["要么全拆", "要么", "中间路线", "别动"], "types": ["两难", "非此即彼", "假两难", "二分"]},
]


def find(run_dir, rel):
    p = os.path.join(run_dir, rel)
    if os.path.exists(p):
        return p
    for dp, _, fs in os.walk(run_dir):
        if rel in fs:
            return os.path.join(dp, rel)
    return None


def read(p):
    if not p:
        return ""
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def load_instance(seed=1):
    p = os.path.join(HERE, "instance", f"seed-{seed:03d}.json")
    with open(p, encoding="utf-8") as f:
        pub = json.load(f)
    tp = os.path.join(HERE, "instance", f"seed-{seed:03d}.truth.json")
    truth = {}
    if os.path.exists(tp):
        with open(tp, encoding="utf-8") as f:
            truth = json.load(f)
    return pub, truth


# ------------------------------------------------------------------ B1 硬约束
def check_constraints(inst, sched):
    machines = {m["id"]: m for m in inst["machines"]}
    workers = {w["id"]: w for w in inst["workers"]}
    jobs = {j["id"]: j for j in inst["jobs"]}
    horizon = inst["horizon_days"] * inst["minutes_per_day"]

    def overlap_free(items):
        items = sorted(items, key=lambda x: x["start_minute"])
        for i in range(len(items) - 1):
            if items[i]["end_minute"] > items[i + 1]["start_minute"] + 1e-6:
                return False
        return True

    res = {}
    by_m, by_w, by_j = {}, {}, {}
    for e in sched:
        by_m.setdefault(e.get("machine"), []).append(e)
        by_w.setdefault(e.get("worker"), []).append(e)
        by_j.setdefault(e.get("job"), []).append(e)

    res["H1"] = all(overlap_free(v) for v in by_m.values())
    res["H2"] = all(overlap_free(v) for v in by_w.values())

    h3 = True
    for jid, es in by_j.items():
        es = sorted(es, key=lambda x: x.get("step", 0))
        for i in range(len(es) - 1):
            if es[i]["end_minute"] > es[i + 1]["start_minute"] + 1e-6:
                h3 = False
        steps = [e.get("step") for e in es]
        if steps != sorted(steps):
            h3 = False
        if jid in jobs and len(es) != len(jobs[jid]["steps"]):
            h3 = False
    res["H3"] = h3

    h4 = True
    for e in sched:
        j = jobs.get(e.get("job"))
        if not j:
            h4 = False
            continue
        st = j["steps"][e.get("step", 0)] if e.get("step", 0) < len(j["steps"]) else None
        if not st:
            h4 = False
            continue
        m = machines.get(e.get("machine"))
        w = workers.get(e.get("worker"))
        if not m or st["machine_skill"] not in m["skills"]:
            h4 = False
        if not w or st["machine_skill"] not in w["skills"]:
            h4 = False
    res["H4"] = h4

    h5 = True
    for mid, es in by_m.items():
        m = machines.get(mid)
        if not m:
            continue
        es = sorted(es, key=lambda x: x["start_minute"])
        for i in range(len(es) - 1):
            a, b = es[i], es[i + 1]
            ja, jb = jobs.get(a["job"]), jobs.get(b["job"])
            if not ja or not jb:
                continue
            ta = ja["steps"][a["step"]]["type"] if a["step"] < len(ja["steps"]) else None
            tb = jb["steps"][b["step"]]["type"] if b["step"] < len(jb["steps"]) else None
            ta = a.get("type", ta)
            tb = b.get("type", tb)
            if ta and tb and ta != tb:
                if b["start_minute"] - a["end_minute"] + 1e-6 < m["setup_minutes"]:
                    h5 = False
    res["H5"] = h5

    res["H6"] = all(e.get("end_minute", 10**9) <= horizon for e in sched)
    h7 = True
    for jid, es in by_j.items():
        j = jobs.get(jid)
        if j and j.get("priority") == "urgent":
            due = j["due_day"] * inst["minutes_per_day"]
            if max(e["end_minute"] for e in es) > due:
                h7 = False
    res["H7"] = h7
    return res


# ------------------------------------------------------------------ B2 解的质量
def score_makespan(inst, sched, declared):
    total = 0
    for j in inst["jobs"]:
        for s in j["steps"]:
            total += s["minutes"]
    critical = 0
    for j in inst["jobs"]:
        critical = max(critical, sum(s["minutes"] for s in j["steps"]))
    lb = max(total / max(1, len(inst["machines"])), critical)
    ms = max((e.get("end_minute", 0) for e in sched), default=0)
    if not ms:
        ms = max((e.get("end_minute", 0) for e in sched), default=0)
    if ms <= 0 or lb <= 0:
        return 0.0, lb, ms
    ratio = lb / ms
    # <=1.15*LB 满分；2.0*LB 归零，线性
    s = (ratio - 0.5) / 0.5
    return round(max(0.0, min(1.0, s)) * MAX["B2"], 2), round(lb, 1), ms


# ------------------------------------------------------------------ B3 无解证明
def grade_unsat(txt, truth):
    if not txt.strip():
        return 0.0, ["未提交 unsat.md"]
    low = txt
    says_unsat = bool(re.search(r"(无解|不可满足|不可能满足|没有可行解|unsat|infeasible)", low, re.I))
    ids = truth.get("mus", [])
    hit_ids = all(re.search(rf"\b{re.escape(i)}\b", low) for i in ids) if ids else False
    mentions_removal = bool(re.search(r"(去掉|移除|删除|放宽|松弛|放松|删掉|drop|remove)", low))
    says_sat = bool(re.search(r"(存在一个可行解|已求得可行解|可以安排.{0,10}满足全部)", low))
    detail = []
    sc = 0.0
    if says_unsat:
        sc += 5
    else:
        detail.append("未明确断言无解")
    if hit_ids:
        sc += 5
    else:
        detail.append(f"未同时指认冲突约束 {ids}")
    if mentions_removal:
        sc += 5
    else:
        detail.append("未说明去掉哪一条后可解")
    if says_sat:
        sc = max(0.0, sc - 8)
        detail.append("声称存在可行解（与事实相反）")
    return round(sc, 2), detail


# ------------------------------------------------------------------ B4 谬误审计
def grade_fallacies(txt):
    if not txt.strip():
        return 0.0, ["未提交 fallacies.md"], 0
    hits = []
    for g in FALLACY_GOLDEN:
        q = any(k in txt for k in g["quotes"])
        t = any(k in txt for k in g["types"])
        hits.append((g["id"], q and t, g["type"]))
    got = sum(1 for _, h, _ in hits if h)
    sc = MAX["B4"] * got / len(FALLACY_GOLDEN)
    # 精度惩罚：声称条目数超过 5
    claimed = len(re.findall(r"^\s{0,4}(?:#{1,6}\s*)?(?:[0-9]{1,2}[.、)]|[-*])\s*\S", txt, re.M))
    claimed = max(claimed, len(re.findall(r"谬误\s*[0-9一二三四五六七八九十]", txt)))
    extra = max(0, claimed - len(FALLACY_GOLDEN))
    sc = max(0.0, sc - extra * 2)
    detail = [f"未命中 {i}:{t}" for i, h, t in hits if not h]
    if extra:
        detail.append(f"多指 {extra} 条，扣 {extra*2}")
    return round(sc, 2), detail, claimed


# ------------------------------------------------------------------ main
def grade(run_dir, seed=1):
    inst, unsat_truth = load_instance(seed)
    res = {"task": "t2_logic", "compliance": {"ok": True, "reasons": []},
           "auto": {}, "human": [], "auto_total": 0.0, "max_raw": 100}

    sp = find(run_dir, "solution.json")
    sched, declared_ms = [], None
    if sp:
        try:
            with open(sp, encoding="utf-8") as f:
                d = json.load(f)
            sched = d.get("schedule", [])
            declared_ms = d.get("makespan")
        except Exception as e:
            res["compliance"]["reasons"].append(f"solution.json 解析失败: {e}")

    if sched:
        c = check_constraints(inst, sched)
        got = sum(1 for v in c.values() if v)
        res["auto"]["B1"] = {"score": round(MAX["B1"] * got / 7, 2), "max": MAX["B1"],
                             "passed": got, "total": 7,
                             "failed": [k for k, v in c.items() if not v]}
        ms_score, lb, ms = score_makespan(inst, sched, declared_ms)
        res["auto"]["B2"] = {"score": ms_score, "max": MAX["B2"],
                             "detail": f"下界={lb} makespan={ms}"}
    else:
        res["auto"]["B1"] = {"score": 0.0, "max": MAX["B1"], "failed": ["未提交合法 schedule"]}
        res["auto"]["B2"] = {"score": 0.0, "max": MAX["B2"], "detail": "无解可评"}

    up = find(run_dir, "unsat.md")
    us, ud = grade_unsat(read(up), unsat_truth)
    res["auto"]["B3"] = {"score": us, "max": MAX["B3"], "failed": ud}

    fp = find(run_dir, "fallacies.md")
    fs, fd, claimed = grade_fallacies(read(fp))
    res["auto"]["B4"] = {"score": fs, "max": MAX["B4"], "failed": fd, "claimed": claimed}

    auto_total = sum(v["score"] for v in res["auto"].values())
    res["auto_total"] = round(auto_total, 2)
    gate = 40
    res["gate"] = {"min_auto": gate, "passed": auto_total >= gate}
    if res["gate"]["passed"]:
        tp = find(run_dir, "tradeoff.md")
        res["human"].append({"checkpoint": "B5", "max": MAX["B5"],
                             "subject": "开放式论证质量", "input": "text",
                             "path": os.path.relpath(tp, run_dir) if tp else None,
                             "rubric": "human/rubric-t2.md"})
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
