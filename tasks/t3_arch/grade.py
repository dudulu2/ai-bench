"""T3 判分器：C1-C5 + bonus 机器判，C6 送人工。

用法: python grade.py --run runs/<model>/t3_arch
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "repo")
HIDDEN = os.path.join(HERE, "tests_hidden")
MAX = {"C1": 10, "C2": 30, "C3": 15, "C4": 20, "C5": 5, "C6": 20}
BONUS = {"C7": 10}
FROZEN = ["CONTRACT.md", "SPEC.md", os.path.join("tests", "test_public.py")]
REQUIRED_SIGNATURES = [
    "def to_base(", "def issue_material(", "def apply_template(", "def get_content(",
    "def get_attachments(", "def report_work(", "def list_exec(", "def summary_qty(",
    "def review_count(", "def settle_count(", "def reconcile(", "def approve_segment(",
    "def reject_doc(", "def void_doc(", "def board_stage(",
]
# 每条现象的根因关键词（命中 >=2 个即认为诊断到位）
GOLDEN_ROOT = {
    "现象一": ["单位", "换算", "kg", "基准", "量纲", "to_base", "需求"],
    "现象二": ["快照", "版本", "template", "模板", "取最新", "min", "max", "解析"],
    "现象三": ["like", "前缀", "归属", "owner", "匹配", "主单", "子单"],
    "现象四": ["事务", "并发", "唯一", "约束", "原子", "锁", "竞态", "提交"],
    "现象五": ["换算", "事务", "丢失更新", "并发", "覆盖", "单位"],
    "现象六": ["计数", "清零", "重置", "作废", "状态机", "投影", "同步", "累加"],
}


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def find_repo(run_dir):
    p = os.path.join(run_dir, "repo")
    if os.path.isdir(p) and os.path.exists(os.path.join(p, "src", "mes.py")):
        return p
    p2 = run_dir
    if os.path.exists(os.path.join(p2, "src", "mes.py")):
        return p2
    for dp, dns, fs in os.walk(run_dir):
        if "mes.py" in fs and os.path.basename(dp) == "src":
            return os.path.dirname(dp)
    return None


def check_compliance(repo):
    reasons = []
    for rel in FROZEN:
        sub = os.path.join(repo, rel)
        base = os.path.join(REPO, rel)
        if not os.path.exists(sub):
            reasons.append(f"冻结文件缺失: {rel}")
            continue
        if os.path.exists(base) and sha(sub) != sha(base):
            reasons.append(f"冻结文件被修改: {rel}")
    mes_py = os.path.join(repo, "src", "mes.py")
    if os.path.exists(mes_py):
        src = open(mes_py, encoding="utf-8", errors="replace").read()
        missing = [s for s in REQUIRED_SIGNATURES if s not in src]
        if missing:
            reasons.append(f"公开入口签名缺失: {missing}")
    else:
        reasons.append("src/mes.py 缺失")
    return {"ok": not reasons, "reasons": reasons}


def run_unittests(workdir, target):
    """Run unittest target and collect each test's actual outcome."""
    import unittest
    old_path = list(sys.path)
    sys.path.insert(0, workdir)
    old_cwd = os.getcwd()
    try:
        os.chdir(workdir)
        for module in list(sys.modules):
            if module == "src" or module.startswith("src.") or module.startswith("tests.") or module.startswith("tests_hidden."):
                del sys.modules[module]
        suite = unittest.defaultTestLoader.loadTestsFromName(target)
        class Collector(unittest.TestResult):
            def __init__(self):
                super().__init__()
                self.outcomes = {}
            def addSuccess(self, test):
                super().addSuccess(test)
                self.outcomes[test.id().split(".")[-2] + "." + test.id().split(".")[-1]] = True
            def addFailure(self, test, err):
                super().addFailure(test, err)
                self.outcomes[test.id().split(".")[-2] + "." + test.id().split(".")[-1]] = False
            def addError(self, test, err):
                super().addError(test, err)
                self.outcomes[test.id().split(".")[-2] + "." + test.id().split(".")[-1]] = False
        result = Collector()
        suite.run(result)
        return result.outcomes
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_path

def grade_answers(repo):
    adir = os.path.join(repo, "_answers")
    found = {}
    if os.path.isdir(adir):
        for f in os.listdir(adir):
            if f.lower().endswith(".json"):
                try:
                    d = json.load(open(os.path.join(adir, f), encoding="utf-8"))
                    found[d.get("题目", f)] = d
                except Exception:
                    pass
    if not found:
        for dp, _, fs in os.walk(repo):
            for f in fs:
                if f.lower().endswith(".json") and ("现象" in f or "answer" in f.lower()):
                    try:
                        d = json.load(open(os.path.join(dp, f), encoding="utf-8"))
                        found[d.get("题目", f)] = d
                    except Exception:
                        pass
    per = MAX["C4"] / 6.0
    sc, detail = 0.0, []
    for phenom, keys in GOLDEN_ROOT.items():
        d = found.get(phenom)
        if not d:
            detail.append(f"{phenom}: 无答复")
            continue
        rc = str(d.get("rootCause", ""))
        hit = sum(1 for k in keys if k.lower() in rc.lower())
        ev = d.get("evidence") or []
        if hit >= 2 and ev:
            sc += per
        elif hit >= 2:
            sc += per * 0.7
            detail.append(f"{phenom}: 缺 evidence")
        else:
            detail.append(f"{phenom}: 根因未命中 ({hit}/{len(keys)})")
    extra = [k for k in found if k not in GOLDEN_ROOT]
    bonus = min(BONUS["C7"], len(extra) * 3)
    return round(sc, 2), detail, bonus, sorted(extra)


def diff_radius(repo):
    """与干净副本对比，统计改动文件数与行数。越小越好。"""
    changed_files, changed_lines = 0, 0
    for rel in ["src/mes.py", "src/db.py", "src/faults.py"]:
        a = os.path.join(REPO, rel)
        b = os.path.join(repo, rel)
        if not (os.path.exists(a) and os.path.exists(b)):
            continue
        la = open(a, encoding="utf-8", errors="replace").read().splitlines()
        lb = open(b, encoding="utf-8", errors="replace").read().splitlines()
        import difflib
        d = list(difflib.unified_diff(la, lb, n=0))
        delta = sum(1 for x in d if x.startswith(("+", "-")) and not x.startswith(("+++", "---")))
        if delta:
            changed_files += 1
            changed_lines += delta
    return changed_files, changed_lines


def grade(run_dir):
    res = {"task": "t3_arch", "compliance": {"ok": True, "reasons": []},
           "auto": {}, "human": [], "auto_total": 0.0, "max_raw": 100}
    repo = find_repo(run_dir)
    if not repo:
        res["compliance"] = {"ok": False, "reasons": ["未找到 repo/src/mes.py"]}
        for k, v in MAX.items():
            res["auto"][k] = {"score": 0.0, "max": v, "failed": ["无提交物"]}
        return res

    comp = check_compliance(repo)
    res["compliance"] = comp
    if not comp["ok"]:
        for k, v in MAX.items():
            res["auto"][k] = {"score": 0.0, "max": v, "failed": comp["reasons"]}
        return res

    work = tempfile.mkdtemp(prefix="t3_")
    try:
        wrepo = os.path.join(work, "repo")
        shutil.copytree(repo, wrepo, ignore=shutil.ignore_patterns("__pycache__", "data.db"))
        os.makedirs(os.path.join(wrepo, "tests_hidden"), exist_ok=True)
        shutil.copy(os.path.join(HIDDEN, "test_hidden.py"), os.path.join(wrepo, "tests_hidden", "test_hidden.py"))
        open(os.path.join(wrepo, "tests_hidden", "__init__.py"), "w").close()

        pub = run_unittests(wrepo, "tests.test_public")
        n_pub = len(pub)
        ok_pub = sum(1 for v in pub.values() if v)
        res["auto"]["C1"] = {"score": round(MAX["C1"] * (ok_pub / n_pub if n_pub else 0), 2),
                             "max": MAX["C1"], "passed": ok_pub, "total": n_pub,
                             "failed": [k for k, v in pub.items() if not v]}

        hid = run_unittests(wrepo, "tests_hidden.test_hidden")
        func_classes = {"TestP1Units", "TestP2Template", "TestP3Attachments"}
        conc_classes = {"TestP4Concurrency", "TestP5Stocktake", "TestP6Approvals"}

        def ratio(classes):
            items = [v for k, v in hid.items() if k.split(".")[0] in classes]
            return (sum(1 for v in items if v) / len(items)) if items else 0.0

        rf, rc_ = ratio(func_classes), ratio(conc_classes)
        res["auto"]["C2"] = {"score": round(MAX["C2"] * rf, 2), "max": MAX["C2"],
                             "failed": [k for k, v in hid.items()
                                        if not v and k.split(".")[0] in func_classes]}
        res["auto"]["C3"] = {"score": round(MAX["C3"] * rc_, 2), "max": MAX["C3"],
                             "failed": [k for k, v in hid.items()
                                        if not v and k.split(".")[0] in conc_classes]}
    finally:
        shutil.rmtree(work, ignore_errors=True)

    c4, detail, bonus, extra = grade_answers(repo)
    res["auto"]["C4"] = {"score": c4, "max": MAX["C4"], "failed": detail}

    files, lines = diff_radius(repo)
    s5 = MAX["C5"]
    if lines == 0:
        s5 = 0.0
    elif lines <= 150 and files <= 3:
        s5 = MAX["C5"]
    elif lines <= 400:
        s5 = round(MAX["C5"] * 0.6, 2)
    else:
        s5 = round(MAX["C5"] * 0.3, 2)
    res["auto"]["C5"] = {"score": s5, "max": MAX["C5"], "detail": f"{files} 文件 / {lines} 行改动"}
    res["auto"]["C7"] = {"score": bonus, "max": BONUS["C7"], "detail": f"额外发现: {extra}"}

    res["auto_total"] = round(sum(v["score"] for v in res["auto"].values()), 2)
    gate = 60
    res["gate"] = {"min_auto": gate, "passed": res["auto_total"] >= gate}
    if res["gate"]["passed"]:
        res["human"].append({"checkpoint": "C6", "max": MAX["C6"],
                             "subject": "工程判断与答复语风", "input": "text",
                             "path": "_answers", "rubric": "human/rubric-t3.md"})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out")
    a = ap.parse_args()
    r = grade(a.run)
    s = json.dumps(r, ensure_ascii=False, indent=2)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(s)
    print(s)


if __name__ == "__main__":
    main()
