"""Regression tests for important scoring invariants."""
import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(rel):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location("module_" + path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BenchRegression(unittest.TestCase):
    def test_t3_public_passes(self):
        grader = load("tasks/t3_arch/grade.py")
        result = grader.grade(str(ROOT / "tasks/t3_arch/repo"))
        self.assertEqual(result["auto"]["C1"]["passed"], 14)
        self.assertEqual(result["auto"]["C1"]["score"], 10)

    def test_t2_claimed_makespan_cannot_override_actual(self):
        grader = load("tasks/t2_logic/grade.py")
        ins, _ = grader.load_instance()
        score, _, actual = grader.score_makespan(ins, [{"end_minute": 10000}], 1)
        self.assertEqual(actual, 10000)
        self.assertEqual(score, 0)

    def test_t2_constraints_accept_nonempty_input(self):
        grader = load("tasks/t2_logic/grade.py")
        ins, _ = grader.load_instance()
        job = ins["jobs"][0]
        st = job["steps"][0]
        machine = next(m for m in ins["machines"] if st["machine_skill"] in m["skills"])
        worker = next(w for w in ins["workers"] if st["machine_skill"] in w["skills"])
        e = {"job": job["id"], "step": 0, "machine": machine["id"],
             "worker": worker["id"], "start_minute": 0, "end_minute": st["minutes"]}
        results = grader.check_constraints(ins, [e])
        self.assertEqual(set(results), {"H1", "H2", "H3", "H4", "H5", "H6", "H7"})


if __name__ == "__main__":
    unittest.main()