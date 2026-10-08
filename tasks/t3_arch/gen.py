"""T3 生成器：产出一份干净的可提交副本，并输出冻结文件基线哈希。

用法:
  python gen.py --hashes                 打印冻结文件基线哈希
  python gen.py --init <dir>             复制一份干净的 repo/ 到目标目录（供模型开工）
"""
import argparse, hashlib, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "repo")
FROZEN = ["CONTRACT.md", "SPEC.md", os.path.join("tests", "test_public.py")]

REQUIRED_SIGNATURES = [
    "def to_base(", "def issue_material(", "def apply_template(", "def get_content(",
    "def get_attachments(", "def report_work(", "def list_exec(", "def summary_qty(",
    "def review_count(", "def settle_count(", "def reconcile(", "def approve_segment(",
    "def reject_doc(", "def void_doc(", "def board_stage(",
]


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hashes", action="store_true")
    ap.add_argument("--init")
    a = ap.parse_args()

    if a.hashes:
        out = {}
        for rel in FROZEN:
            p = os.path.join(REPO, rel)
            out[rel] = sha(p) if os.path.exists(p) else None
        import json
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return

    if a.init:
        dst = os.path.join(a.init, "repo")
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(REPO, dst, ignore=shutil.ignore_patterns("_answers", "__pycache__", "data.db"))
        os.makedirs(os.path.join(dst, "_answers"), exist_ok=True)
        print(f"initialized {dst}")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
