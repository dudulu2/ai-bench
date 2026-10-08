"""T6 判分器：F1-F2 机器判，F3/F4 送人工（盲评文本，先打分后看机器分）。

用法: python grade.py --run runs/<model>/t6_writing
"""
import argparse, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
MAX = {"F1": 30, "F2": 10, "F3": 40, "F4": 20}

BANNED_PATTERNS = [
    (r"剖腹|剪开.{0,4}(狼|肚子)|肚子里.{0,6}(出来|跳出)|把.{0,3}狼.{0,4}(打死|开枪).{0,10}(救出|救出外婆)", "狼被剖腹救出的桥段"),
    (r"假扮.{0,4}外婆|装成.{0,4}外婆|穿上.{0,6}(外婆|睡衣).{0,8}床|躺在床上.{0,8}等", "狼假扮外婆躺在床上"),
    (r"从此.{0,14}(幸福|快乐)|幸福地生活在一起|圆满结局", "童话套话结尾"),
]
META_PATTERNS = [
    (r"^\s*(创作谈|后记|作者按|说明|注：|附注)", "含元文本小标题"),
    (r"(共\s*\d+\s*字|字数[:：]|以下是我的创作|希望你喜欢)", "含字数统计或作者说明"),
]


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


def count_chars(text):
    """中文按字计，英文按词计，取合计。"""
    cn = len(re.findall(r"[\u4e00-\u9fff]", text))
    en = len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text))
    return cn + en


def grade(run_dir, seed=1):
    truth = load_truth(seed)
    res = {"task": "t6_writing", "compliance": {"ok": True, "reasons": []},
           "auto": {}, "human": [], "auto_total": 0.0, "max_raw": 100}

    p = find(run_dir, "story.md")
    text = ""
    if p:
        text = open(p, encoding="utf-8", errors="replace").read()
    if not text:
        res["compliance"] = {"ok": False, "reasons": ["未找到 story.md"]}
        for k, v in MAX.items():
            res["auto"][k] = {"score": 0.0, "max": v, "failed": ["无提交物"]}
        return res

    # ---- F1 硬约束
    checks = []
    required = truth.get("required_chars", [])
    present = [c for c in required if c in text]
    checks.append((f"四个主角全部出现 ({len(present)}/{len(required)})",
                   len(present) == len(required), f"缺 {[c for c in required if c not in text]}"))

    # 「有戏份」近似：该角色被提及 >= 2 次
    thin = [c for c in present if len(re.findall(re.escape(c), text)) < 2]
    checks.append(("每位主角至少被提及 2 次（有戏份）", not thin, f"戏份过薄: {thin}"))

    n = count_chars(text)
    lo, hi = truth.get("word_min", 800), truth.get("word_max", 1600)
    checks.append((f"字数在区间 ({n} / {lo}-{hi})", lo <= n <= hi, f"实到 {n}"))

    hits = [d for pat, d in BANNED_PATTERNS if re.search(pat, text)]
    checks.append(("无禁止桥段", not hits, f"命中: {hits}"))

    first = text.strip().splitlines()[0] if text.strip() else ""
    checks.append(("有标题", bool(first) and len(first) <= 40 and not first.startswith("#" * 4),
                   f"首行: {first[:30]}"))

    # 配角戏份：正文里出现的人名（不含四位主角）不应喧宾夺主 —— 用提及次数占比近似
    STOP = {"他", "她", "它", "我", "你", "们", "自己", "有人", "没人", "谁", "大家", "别人", "那人"}
    extras = set(re.findall(r"[\u4e00-\u9fff]{2,3}(?=(?:说|道|问|答|笑|站|走))", text))
    extras = {e for e in extras
              if e not in required and not any(w in e for w in STOP)
              and not re.search(r"[的了着过是也就都又还很]", e)}
    over = [e for e in extras if len(re.findall(re.escape(e), text)) >
            min(len(re.findall(re.escape(c), text)) for c in present or [""])]
    checks.append(("配角戏份未超过最少的主角", not over, f"越界配角: {list(over)[:5]}"))

    got = sum(1 for _, ok_, _ in checks if ok_)
    res["auto"]["F1"] = {"score": round(MAX["F1"] * got / len(checks), 2), "max": MAX["F1"],
                         "passed": got, "total": len(checks),
                         "failed": [f"{nm}({m})" for nm, ok_, m in checks if not ok_],
                         "chars": n}

    # ---- F2 逻辑自洽与伏笔
    c2 = []
    first_person = len(re.findall(r"(?<![\u4e00-\u9fff])我(?!们)", text))
    third_person = len(re.findall(r"小红帽", text))
    c2.append(("人称/视角一致", not (first_person > 5 and third_person > 5),
               f"第一人称 {first_person} 次 / 第三人称 {third_person} 次 混用"))

    meta = [d for pat, d in META_PATTERNS if re.search(pat, text, re.M)]
    c2.append(("正文干净（无后记/字数统计）", not meta, f"命中: {meta}"))

    # 伏笔回收：显式设悬的词（"后来""直到最后"）应在后文出现对应回收词
    setups = len(re.findall(r"(直到.{0,6}(最后|那天)|后来才|谁也没有注意|没人发现)", text))
    payoffs = len(re.findall(r"(原来|这才明白|终于想起|正是那|当初那)", text))
    c2.append(("伏笔与回收配平", payoffs >= setups, f"设悬 {setups} 处 / 回收 {payoffs} 处"))

    got2 = sum(1 for _, ok_, _ in c2 if ok_)
    res["auto"]["F2"] = {"score": round(MAX["F2"] * got2 / len(c2), 2), "max": MAX["F2"],
                         "passed": got2, "total": len(c2),
                         "failed": [f"{nm}({m})" for nm, ok_, m in c2 if not ok_]}

    res["auto_total"] = round(sum(v["score"] for v in res["auto"].values()), 2)
    gate = 20
    res["gate"] = {"min_auto": gate, "passed": res["auto_total"] >= gate}
    if res["gate"]["passed"]:
        res["human"].append({"checkpoint": "F3", "max": MAX["F3"], "subject": "文学性",
                             "input": "text", "path": os.path.relpath(p, run_dir),
                             "rubric": "human/rubric-t6.md"})
        res["human"].append({"checkpoint": "F4", "max": MAX["F4"], "subject": "结构与节奏",
                             "input": "text", "path": os.path.relpath(p, run_dir),
                             "rubric": "human/rubric-t6.md"})
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
