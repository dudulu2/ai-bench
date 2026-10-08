"""ai-bench 一键流水线。

  python runner/run.py grade --run runs/<model>/<ts> [--tasks t1_spec,t2_logic]
  python runner/run.py human-queue
  python runner/run.py report --run runs/<model>/<ts>
  python runner/run.py site
"""
import argparse, json, os, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runner"))
import yamlish  # noqa: E402

BENCH = yamlish.load(os.path.join(ROOT, "bench.yaml"))
TASKS = BENCH["tasks"]
DIRECTIONS = BENCH["directions"]

GRADERS = {k: os.path.join(ROOT, "tasks", k, "grade.py") for k in TASKS}


def runs_root():
    return os.path.join(ROOT, "runs")


def list_runs():
    base = runs_root()
    out = []
    if not os.path.isdir(base):
        return out
    for model in sorted(os.listdir(base)):
        mdir = os.path.join(base, model)
        if not os.path.isdir(mdir):
            continue
        for ts in sorted(os.listdir(mdir)):
            p = os.path.join(mdir, ts)
            if os.path.isdir(p):
                out.append((model, ts, p))
    return out


# ------------------------------------------------------------------ grade
def grade_run(run_dir, only=None, seed=1):
    results = {}
    outdir = os.path.join(run_dir, "scores")
    os.makedirs(outdir, exist_ok=True)
    for tid in TASKS:
        if only and tid not in only:
            continue
        sub = os.path.join(run_dir, tid)
        if not os.path.isdir(sub):
            sub = run_dir if os.path.exists(os.path.join(run_dir, "src", "mes.py")) else sub
        if not os.path.isdir(sub):
            results[tid] = {"task": tid, "compliance": {"ok": False, "reasons": ["未提交"]},
                            "auto": {}, "human": [], "auto_total": 0.0, "max_raw": TASKS[tid]["max_raw"]}
            continue
        gp = GRADERS[tid]
        if not os.path.exists(gp):
            results[tid] = {"task": tid, "compliance": {"ok": False, "reasons": [f"缺判分器 {gp}"]},
                            "auto": {}, "human": [], "auto_total": 0.0}
            continue
        print(f"[grade] {tid} ...", flush=True)
        try:
            p = subprocess.run([sys.executable, gp, "--run", sub, "--seed", str(seed),
                                "--out", os.path.join(outdir, f"{tid}.json")],
                               capture_output=True, text=True, timeout=900, cwd=ROOT)
            if p.returncode != 0:
                print(p.stdout[-2000:], p.stderr[-2000:])
            r = json.load(open(os.path.join(outdir, f"{tid}.json"), encoding="utf-8"))
        except Exception as e:
            r = {"task": tid, "compliance": {"ok": False, "reasons": [f"判分异常: {e}"]},
                 "auto": {}, "human": [], "auto_total": 0.0}
        results[tid] = r
    summary = summarize(results, run_dir)
    with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def load_human_scores():
    p = os.path.join(ROOT, "human", "scores.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def hkey(model, ts, tid, cp):
    return f"{model}@{ts}/{tid}/{cp}"


def summarize(results, run_dir=None):
    model_ts = (os.path.basename(os.path.dirname(run_dir)), os.path.basename(run_dir)) if run_dir else None
    total_auto, total_human, total_pending = 0.0, 0.0, 0.0
    per_task = {}
    hs = load_human_scores()
    for tid, r in results.items():
        auto = r.get("auto_total", 0.0) or 0.0
        total_auto += auto
        human_got, pending = 0.0, 0.0
        for h in r.get("human", []):
            cp = h["checkpoint"]
            k = hkey(*model_ts, tid, cp) if model_ts else None
            v = hs.get(k) if k else None
            if v is None:
                pending += h["max"]
            else:
                human_got += v
        total_human += human_got
        total_pending += pending
        per_task[tid] = {"auto": round(auto, 2), "human": round(human_got, 2),
                         "pending_human": round(pending, 2),
                         "max": TASKS[tid].get("max_raw", 100),
                         "gate": r.get("gate"), "compliance": r.get("compliance")}
    return {"auto_total": round(total_auto, 2), "human_total": round(total_human, 2),
            "pending_human": round(total_pending, 2),
            "total": round(total_auto + total_human, 2),
            "max_total": BENCH.get("total_ref", 600),
            "tasks": per_task}


def apply_directions(summary, run_dir):
    """给 summary 补方向分。"""
    model = os.path.basename(os.path.dirname(run_dir))
    ts = os.path.basename(run_dir)
    hs = load_human_scores()
    task_score = {}
    for tid in TASKS:
        r_path = os.path.join(run_dir, "scores", f"{tid}.json")
        auto, hum = 0.0, 0.0
        if os.path.exists(r_path):
            r = json.load(open(r_path, encoding="utf-8"))
            auto = r.get("auto_total", 0.0) or 0.0
            for h in r.get("human", []):
                v = hs.get(hkey(model, ts, tid, h["checkpoint"]))
                if v is not None:
                    hum += v
        task_score[tid] = auto + hum
    dirs = {}
    for dk, d in DIRECTIONS.items():
        w = d.get("weights") or {}
        s = sum(task_score.get(t, 0.0) * wt for t, wt in w.items())
        dirs[dk] = round(s, 2)
    summary["directions"] = dirs
    return summary


# ------------------------------------------------------------------ human queue
def build_human_queue():
    hdir = os.path.join(ROOT, "human")
    assets = os.path.join(hdir, "assets")
    os.makedirs(assets, exist_ok=True)
    hs = load_human_scores()
    items = []
    for model, ts, run_dir in list_runs():
        sdir = os.path.join(run_dir, "scores")
        if not os.path.isdir(sdir):
            continue
        for tid in TASKS:
            p = os.path.join(sdir, f"{tid}.json")
            if not os.path.exists(p):
                continue
            try:
                r = json.load(open(p, encoding="utf-8"))
            except Exception:
                continue
            for h in r.get("human", []):
                k = hkey(model, ts, tid, h["checkpoint"])
                entry = {"key": k, "model": model, "ts": ts, "task": tid,
                         "checkpoint": h["checkpoint"], "subject": h.get("subject"),
                         "max": h["max"], "input": h.get("input", "text"),
                         "rubric": h.get("rubric"), "scored": hs.get(k)}
                if h.get("input") == "images":
                    shots = []
                    for i, rel in enumerate(h.get("shots", [])):
                        src = os.path.join(run_dir, tid, rel)
                        if not os.path.exists(src):
                            src = os.path.join(run_dir, rel)
                        if os.path.exists(src):
                            dst = os.path.join(assets, f"{k.replace('/', '_').replace('@', '_')}_{i}.png")
                            shutil.copy(src, dst)
                            shots.append(os.path.relpath(dst, hdir))
                    entry["assets"] = shots
                else:
                    src = os.path.join(run_dir, tid, h.get("path", "")) if h.get("path") else None
                    if h.get("path") == "_answers":
                        src = os.path.join(run_dir, tid, "repo", "_answers")
                    txt = ""
                    if src and os.path.isdir(src):
                        for f in sorted(os.listdir(src)):
                            if f.endswith(".json"):
                                txt += f"--- {f} ---\n" + open(os.path.join(src, f), encoding="utf-8",
                                                              errors="replace").read() + "\n"
                    elif src and os.path.exists(src):
                        txt = open(src, encoding="utf-8", errors="replace").read()
                    entry["text"] = txt[:8000]
                items.append(entry)
    with open(os.path.join(hdir, "queue.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "scale": BENCH["human"]["scale"], "items": items}, f, ensure_ascii=False, indent=2)
    print(f"[human-queue] {len(items)} 项待评 -> human/queue.json")
    pending = [i for i in items if i.get("scored") is None]
    print(f"[human-queue] 其中未评分 {len(pending)} 项")
    return items


# ------------------------------------------------------------------ site
def build_site():
    sdir = os.path.join(ROOT, "site")
    os.makedirs(sdir, exist_ok=True)
    rows = []
    for model, ts, run_dir in list_runs():
        sp = os.path.join(run_dir, "summary.json")
        if not os.path.exists(sp):
            continue
        s = json.load(open(sp, encoding="utf-8"))
        s = apply_directions(s, run_dir)
        rows.append({"model": model, "ts": ts, **s})
    rows.sort(key=lambda r: -r.get("total", 0))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    data = {"updated": time.strftime("%Y-%m-%d"),
            "total_ref": BENCH.get("total_ref"),
            "tasks": {k: {"zh": v.get("zh"), "name": v.get("name"), "order": v.get("order"),
                          "max_raw": v.get("max_raw"), "human_share": v.get("human_share")}
                      for k, v in TASKS.items()},
            "directions": {k: {"zh": v.get("zh"), "en": v.get("en")} for k, v in DIRECTIONS.items()},
            "rows": rows}
    with open(os.path.join(sdir, "board.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[site] {len(rows)} 条记录 -> site/board.json")
    return data


# ------------------------------------------------------------------ cli
def main():
    ap = argparse.ArgumentParser(prog="run.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("grade")
    g.add_argument("--run", required=True)
    g.add_argument("--tasks")
    g.add_argument("--seed", type=int, default=1)

    sub.add_parser("human-queue")
    sub.add_parser("site")

    r = sub.add_parser("report")
    r.add_argument("--run", required=True)

    a = ap.parse_args()
    if a.cmd == "grade":
        only = set(filter(None, (a.tasks or "").split(","))) or None
        run_dir = a.run if os.path.isabs(a.run) else os.path.join(ROOT, a.run)
        s = grade_run(run_dir, only, a.seed)
        s = apply_directions(s, run_dir)
        json.dump(s, open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(json.dumps(s, ensure_ascii=False, indent=2))
    elif a.cmd == "human-queue":
        build_human_queue()
    elif a.cmd == "site":
        build_site()
    elif a.cmd == "report":
        run_dir = a.run if os.path.isabs(a.run) else os.path.join(ROOT, a.run)
        print(open(os.path.join(run_dir, "summary.json"), encoding="utf-8").read())


if __name__ == "__main__":
    main()
