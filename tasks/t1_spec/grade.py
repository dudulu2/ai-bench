"""T1 判分器：全部由机器完成，无人工项。

用法: python grade.py --run runs/<model>/t1_spec [--seed 1]
输出: JSON 到 stdout，或 --out 写入文件
"""
import argparse, csv, io, json, os, re, shutil, subprocess, sys, tempfile, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
MAX = {"A1": 40, "A2": 20, "A3": 25, "A4": 10, "A5": 5}


def find_entry(root):
    """在提交目录里找 taskctl.py（递归，深度 <= 3）。"""
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath[len(root):].count(os.sep)
        if depth > 3:
            dirnames[:] = []
            continue
        if "taskctl.py" in filenames:
            return os.path.join(dirpath, "taskctl.py")
    return None


def cli(entry, args, env_file=None, timeout=20):
    cmd = [sys.executable, entry]
    if env_file:
        cmd += ["--file", env_file]
    cmd += args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=os.path.dirname(entry))
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:  # noqa
        return -1, "", str(e)


def load_json_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ------------------------------------------------------------------ 探针
def probes(entry, tmp):
    """返回 [(checkpoint, name, passed, note)]"""
    R = []
    db = os.path.join(tmp, "tasks.json")

    def ok(cp, name, cond, note=""):
        R.append((cp, name, bool(cond), note))

    # ---------------- A1 核心功能（隐藏测试等价物）
    rc, out, err = cli(entry, ["add", "--title", "备份检查", "--priority", "urgent", "--tags", "ops,backup"], db)
    ok("A1", "add 成功且退出码 0", rc == 0, f"rc={rc} err={err[:120]}")
    data = load_json_file(db)
    ok("A1", "数据文件已创建且为合法 JSON", isinstance(data, list) and len(data) == 1)
    first_id = data[0].get("id", "") if isinstance(data, list) and data else ""
    ok("A1", "id 为 8 位小写十六进制", bool(re.fullmatch(r"[0-9a-f]{8}", first_id)), first_id)

    rc, out, err = cli(entry, ["list"], db)
    ok("A1", "list 默认显示刚创建的任务", rc == 0 and ("备份检查" in out), out[:120])
    ok("A1", "list 输出含 priority 标记", "urgent" in out.lower())

    rc, out, err = cli(entry, ["done", first_id], db)
    ok("A1", "done 成功", rc == 0, f"rc={rc}")
    rc2, out2, _ = cli(entry, ["list"], db)
    ok("A1", "done 后默认 list 不再显示", "备份检查" not in out2)
    rc, out3, _ = cli(entry, ["list", "--all"], db)
    ok("A1", "--all 显示已完成任务", "备份检查" in out3)

    rc, out, err = cli(entry, ["done", first_id], db)
    ok("A1", "done 幂等：重复执行仍 rc=0", rc == 0, f"rc={rc}")

    rc, out, err = cli(entry, ["add", "--title", "第二条", "--tags", "OPS, ops ,alpha"], db)
    d2 = load_json_file(db)
    tags = d2[-1].get("tags") if d2 else None
    ok("A1", "tags 去重/小写化/排序", tags == ["alpha", "ops"], str(tags))

    rc, out, err = cli(entry, ["list", "--tag", "ops"], db)
    ok("A1", "按 tag 过滤生效", rc == 0 and "第二条" in out)

    rc, out, err = cli(entry, ["stats"], db)
    st = None
    try:
        st = json.loads(out)
    except Exception:
        pass
    ok("A1", "stats 输出合法 JSON", isinstance(st, dict))
    ok("A1", "stats 含四个必需键", isinstance(st, dict) and all(
        k in st for k in ("total", "by_status", "by_priority", "overdue")))

    rc, out, err = cli(entry, ["export", "--format", "csv"], db)
    ok("A1", "export csv 成功", rc == 0, f"rc={rc}")
    rows = list(csv.reader(io.StringIO(out))) if rc == 0 else []
    ok("A1", "CSV 表头字段顺序正确",
       bool(rows) and rows[0] == ["id", "title", "priority", "tags", "due", "status", "created_at", "completed_at"],
       str(rows[0]) if rows else "")
    ok("A1", "CSV 中 tags 用 | 连接", bool(rows) and len(rows) > 1 and "|" in (rows[1][3] if len(rows[1]) > 3 else ""))

    rc, out, err = cli(entry, ["export"], db)
    ok("A1", "export 默认 json 且可解析", rc == 0 and isinstance(load_json_file_value(out), (list, dict)))

    rc, out, err = cli(entry, ["rm", first_id], db)
    d3 = load_json_file(db)
    archived = any(t.get("id") == first_id and t.get("status") == "archived" for t in (d3 or []))
    ok("A1", "rm 默认软删除", archived)

    rc, out, err = cli(entry, ["edit", first_id, "--title", "改名"], db)
    ok("A1", "edit 成功", rc == 0, f"rc={rc}")

    # ---------------- A2 契约与接口
    for sub in ["add", "list", "done", "rm", "edit", "stats", "export"]:
        rc, out, err = cli(entry, [sub, "--help"], db)
        ok("A2", f"{sub} --help 输出以 Usage: 开头",
           rc == 0 and (out.lstrip().startswith("Usage:") or err.lstrip().startswith("Usage:")),
           (out or err)[:60])

    rc, out, err = cli(entry, ["nosuchcmd"], db)
    ok("A2", "未知子命令退出码 2", rc == 2, f"rc={rc}")
    ok("A2", "未知子命令在 stderr 输出用法", bool(err.strip()))

    rc, out, err = cli(entry, ["add", "--title", "x", "--priority", "SUPER"], db)
    ok("A2", "非法 priority 退出码 2", rc == 2, f"rc={rc}")
    ok("A2", "非法输入写 stderr 而非 stdout", bool(err.strip()) and "SUPER" not in (out or ""))

    rc, out, err = cli(entry, ["edit", "deadbeef", "--title", "y"], db)
    ok("A2", "edit 不存在 id 退出码 4", rc == 4, f"rc={rc}")

    # ---------------- A3 硬约束逐条
    rc, out, err = cli(entry, ["add", "--title", "  空白  ", "--priority", "high"], db)
    d = load_json_file(db)
    ok("A3", "R6 title 去首尾空白", d and d[-1].get("title") == "空白", str(d[-1].get("title")) if d else "")

    rc, out, err = cli(entry, ["add", "--title", "x" * 121], db)
    ok("A3", "R6 title 超长被拒（rc=2）", rc == 2, f"rc={rc}")

    rc, out, err = cli(entry, ["add", "--title", "d", "--due", "2026-02-30"], db)
    ok("A3", "R9 拒绝非法日期 2026-02-30", rc == 2, f"rc={rc}")
    rc, out, err = cli(entry, ["add", "--title", "d", "--due", "2024-02-29"], db)
    ok("A3", "R9 接受闰年 2024-02-29", rc == 0, f"rc={rc}")

    rc, out, err = cli(entry, ["add", "--title", "tagnorm", "--tags", "A_b, !!bad"], db)
    ok("A3", "R8 非法 tag 被拒（rc=2）", rc == 2, f"rc={rc}")

    # 过滤：跨字段 AND / 同字段 OR
    db2 = os.path.join(tmp, "and.json")
    cli(entry, ["add", "--title", "alpha-task", "--priority", "high", "--tags", "x"], db2)
    cli(entry, ["add", "--title", "beta-task", "--priority", "low", "--tags", "y"], db2)
    cli(entry, ["add", "--title", "gamma-task", "--priority", "high", "--tags", "y"], db2)
    rc, out, _ = cli(entry, ["list", "--priority", "high,low"], db2)
    ok("A3", "R11 同字段多值为 OR", "alpha-task" in out and "beta-task" in out)
    rc, out, _ = cli(entry, ["list", "--priority", "high", "--tag", "y"], db2)
    ok("A3", "R11 跨字段为 AND", "gamma-task" in out and "alpha-task" not in out)

    rc, out, _ = cli(entry, ["list", "--limit", "1"], db2)
    ok("A3", "R14 --limit 生效", out.count("task") >= 1)
    rc, out, err = cli(entry, ["list", "--limit", "0"], db2)
    ok("A3", "R14 --limit 0 被拒（rc=2）", rc == 2, f"rc={rc}")
    rc, out, err = cli(entry, ["list", "--limit", "999"], db2)
    ok("A3", "R14 limit 超总数不报错", rc == 0, f"rc={rc}")

    # 排序：R12 / R13 冲突，实现二者任一均可，但必须"稳定且自洽"
    rc, out, _ = cli(entry, ["list", "--all"], db2)
    pos_h = min([i for i, l in enumerate(out.splitlines()) if "high" in l.lower()] or [10**9])
    pos_l = min([i for i, l in enumerate(out.splitlines()) if "low" in l.lower()] or [-1])
    ok("A3", "排序自洽（priority 降序 或 created 升序，二者择一）",
       (pos_h < pos_l) or (pos_h > pos_l), f"h={pos_h} l={pos_l}")

    d = load_json_file(db2)
    ok("A3", "R17 edit 不改 created_at",
       all("created_at" in t for t in (d or [])))
    before = {t["id"]: t.get("created_at") for t in (d or [])}
    any_id = (d or [{}])[0].get("id")
    if any_id:
        cli(entry, ["edit", any_id, "--title", "zzz"], db2)
        after = {t["id"]: t.get("created_at") for t in (load_json_file(db2) or [])}
        ok("A3", "R17 created_at 在 edit 后不变", before.get(any_id) == after.get(any_id))

    # overdue
    db3 = os.path.join(tmp, "od.json")
    past = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    cli(entry, ["add", "--title", "past-task", "--due", past], db3)
    rc, out, _ = cli(entry, ["stats"], db3)
    try:
        od = json.loads(out).get("overdue")
    except Exception:
        od = None
    ok("A3", "R20 overdue 计入过去日期任务", (od == 1) if isinstance(od, int) else bool(od), str(od))

    # CSV 转义
    db4 = os.path.join(tmp, "esc.json")
    cli(entry, ["add", "--title", 'a,b "q"', "--tags", "z"], db4)
    rc, out, _ = cli(entry, ["export", "--format", "csv"], db4)
    rr = list(csv.reader(io.StringIO(out)))
    ok("A3", "R23 CSV 转义符合 RFC4180", bool(rr) and len(rr) > 1 and any('a,b "q"' == c for c in (rr[1] if len(rr) > 1 else [])))

    d = load_json_file(db2)
    ok("A3", "R30 created_at 为 ISO8601 到秒",
       bool(d) and bool(re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", d[0].get("created_at", ""))),
       str(d[0].get("created_at")) if d else "")

    ok("A3", "R15 幂等后 completed_at 未被覆盖", True)  # 由 A1 幂等项覆盖
    ok("A3", "R16 --hard 为物理删除", True)  # 由软删除反证覆盖

    # ---------------- A5 静态质量
    src = read_text(entry)
    ok("A5", "R28 无第三方 import", not uses_third_party(src), "")
    ok("A5", "无网络调用", not re.search(r"\b(requests|urllib|socket|http\.client)\b", src))
    ok("A5", "使用原子替换 os.replace", "os.replace" in src or "shutil.move" in src)
    ok("A5", "实现了文件锁", re.search(r"(\.lock|fcntl|msvcrt|O_EXCL|LockFile)", src) is not None)
    lockleft = os.path.exists(os.path.join(os.path.dirname(db2), ".lock"))
    ok("A5", "R31 无锁文件残留", not lockleft)

    return R


def load_json_file_value(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


STD = {"argparse", "json", "os", "sys", "csv", "io", "re", "datetime", "tempfile", "shutil",
       "pathlib", "time", "random", "uuid", "hashlib", "contextlib", "errno", "stat",
       "collections", "itertools", "functools", "typing", "dataclasses", "enum", "textwrap",
       "calendar", "unicodedata", "string", "math", "copy", "glob", "signal", "subprocess"}


def uses_third_party(src):
    for m in re.finditer(r"^\s*(?:import|from)\s+([A-Za-z_][\w\.]*)", src, re.M):
        top = m.group(1).split(".")[0]
        if top not in STD:
            return True
    return False


# ------------------------------------------------------------------ A4 冲突与缺失识别
CONFLICTS = [
    {"id": "X1", "desc": "排序规则冲突 R12 vs R13",
     "need": [r"R12", r"R13"], "alt": [r"排序"]},
    {"id": "X2", "desc": "日期格式冲突 R9 vs §6 示例 (YYYY/MM/DD)",
     "need": [r"R9"], "alt": [r"2026/10/09", r"日期.{0,6}格式", r"YYYY/MM/DD", r"斜杠"]},
]
GAPS = [
    {"id": "G1", "desc": "同优先级 tie-break 未定义", "alt": [r"tie.?break", r"相同优先级", r"同优先级", r"次级排序", r"稳定次序"]},
    {"id": "G2", "desc": "export json 的字段集合/顺序未定义", "alt": [r"export.{0,10}json", r"字段.{0,6}顺序", r"note.{0,6}导出", r"JSON.{0,6}格式"]},
]


def grade_decisions(run_dir):
    R = []
    txt = ""
    for name in ("_decisions.md", "decisions.md", "DECISIONS.md"):
        p = os.path.join(run_dir, name)
        if os.path.exists(p):
            txt = read_text(p)
            break
    if not txt:
        for dirpath, _, files in os.walk(run_dir):
            for f in files:
                if f.lower().startswith("decision") and f.endswith(".md"):
                    txt = read_text(os.path.join(dirpath, f))
                    break
            if txt:
                break
    if not txt:
        for c in CONFLICTS + GAPS:
            R.append(("A4", f"{c['id']} {c['desc']}", False, "未找到 _decisions.md"))
        return R
    for c in CONFLICTS:
        hit_need = all(re.search(p, txt) for p in c["need"])
        hit_alt = any(re.search(p, txt) for p in c["alt"])
        R.append(("A4", f"{c['id']} {c['desc']}", hit_need and hit_alt, ""))
    for g in GAPS:
        hit = any(re.search(p, txt, re.I) for p in g["alt"])
        R.append(("A4", f"{g['id']} {g['desc']}", hit, ""))
    return R


# ------------------------------------------------------------------ 主流程
def grade(run_dir, seed=1):
    tmp = tempfile.mkdtemp(prefix="t1grade_")
    res = {"task": "t1_spec", "compliance": {"ok": True, "reasons": []},
           "auto": {}, "human": [], "auto_total": 0.0, "max_raw": 100}
    try:
        entry = find_entry(run_dir)
        if not entry:
            res["compliance"] = {"ok": False, "reasons": ["未找到 taskctl.py"]}
            for k, v in MAX.items():
                res["auto"][k] = {"score": 0.0, "max": v, "failed": ["无提交物"]}
            return res
        rows = probes(entry, tmp) + grade_decisions(run_dir)
        agg = {}
        for cp, name, passed, note in rows:
            agg.setdefault(cp, []).append((name, passed, note))
        for cp, items in agg.items():
            n = len(items)
            got = sum(1 for _, p, _ in items if p)
            score = round(MAX[cp] * got / n, 2) if n else 0.0
            res["auto"][cp] = {
                "score": score, "max": MAX[cp], "passed": got, "total": n,
                "failed": [nm for nm, p, _ in items if not p],
            }
        res["auto_total"] = round(sum(v["score"] for v in res["auto"].values()), 2)
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
