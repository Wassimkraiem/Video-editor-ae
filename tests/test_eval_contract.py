import json
from pathlib import Path


def test_fixed_eval_set_has_ten_cases():
    cases = json.loads(Path("evals/quality_eval_set.json").read_text(encoding="utf-8"))
    assert len(cases) == 10
    assert {case["kind"] for case in cases} == {"talking-head", "motion-graphics", "explainer", "social-reframe"}
