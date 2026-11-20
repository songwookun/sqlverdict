import json
from datetime import date
from decimal import Decimal

import pytest

from sqlverdict import __version__
from sqlverdict.model import Golden, GoldenItem, PredItem, Predictions, Result
from sqlverdict.score import _baseline_diff, _group, _score_item, _summary, score

EXP = Result(["customer_id", "order_count"], [("A", 12), ("B", 9)])


def G(**kw):
    base = dict(id="q1", question="질문", expected=EXP, level="L4", trap="dup_join",
                why="w", verified=True)
    return GoldenItem(**{**base, **kw})


def P(rows=(("A", 12), ("B", 9)), cols=("customer_id", "order_count"), **kw):
    return PredItem(id="q1", result=Result(list(cols), [tuple(r) for r in rows]), **kw)


def S(it, pred, **kw):
    return _score_item(it, pred, golden_dialect=kw.pop("golden_dialect", "mysql"),
                       pred_dialect=kw.pop("pred_dialect", None),
                       tolerance=kw.pop("tolerance", 0.001), **kw)


def test_correct_record_shape():
    rec = S(G(), P())
    assert rec["label"] == "correct"
    assert (rec["id"], rec["level"], rec["trap"]) == ("q1", "L4", "dup_join")
    assert rec["diff"]["matched_by"] == "name" and rec["hints"] == []


def test_broken_golden_is_unscorable_even_with_pred():
    rec = S(G(problem="알 수 없는 필드: orderd", expected=None), P())
    assert rec["label"] == "unscorable" and "orderd" in rec["reason"]


def test_unverified_skipped_unless_included():
    assert S(G(verified=False), P())["label"] == "skipped_unverified"
    assert S(G(verified=False), P(), include_unverified=True)["label"] == "correct"


def test_unverified_beats_missing_prediction():
    assert S(G(verified=False), None)["label"] == "skipped_unverified"


def test_missing_prediction():
    assert S(G(), None)["label"] == "missing_prediction"


def test_broken_pred_is_unscorable():
    rec = S(G(), PredItem(id="q1", problem="result와 error 중 정확히 하나가 필요합니다"))
    assert rec["label"] == "unscorable" and "result" in rec["reason"]


def test_error_kept_and_truncated():
    rec = S(G(), PredItem(id="q1", error="Unknown column 'order_dt'"))
    assert rec["label"] == "error" and rec["error"] == "Unknown column 'order_dt'"
    assert len(S(G(), PredItem(id="q1", error="x" * 1000))["error"]) == 300


def test_dup_join_gets_hint():
    rec = S(G(), P(rows=(("A", 24), ("B", 18)), pred_sql="SELECT * FROM orders"))
    assert rec["label"] == "silent_wrong" and rec["diff"]["ratio"] == 2.0
    assert rec["hints"] == ["값이 정확히 2배: 중복 조인·필터 누락 의심", "SELECT * 사용: 필요한 컬럼만 고르세요"]


def test_item_tolerance_zero_overrides_global():
    it = G(expected=Result(["avg"], [(152340.3333,)]))
    pred = P(rows=((152340.33,),), cols=("avg",))
    assert S(it, pred)["label"] == "correct_approx"
    assert S(G(expected=it.expected, tolerance=0), pred)["label"] == "silent_wrong"


def test_pred_dialect_falls_back_to_golden():
    it = G(expected=Result(["memo"], [("",)]))
    pred = P(rows=(("",),), cols=("memo",))
    assert S(it, pred, golden_dialect="mysql")["label"] == "correct"
    assert S(it, pred, golden_dialect="mysql", pred_dialect="oracle")["label"] == "silent_wrong"


def test_values_excluded_by_default():
    rec = S(G(expected=Result(["name"], [("홍길동",)])), P(rows=(("김철수",),), cols=("name",)))
    text = json.dumps(rec, ensure_ascii=False)
    assert "홍길동" not in text and "김철수" not in text
    assert "got_head" not in rec and "expected" not in rec


def test_head_and_include_expected():
    rec = S(G(), P(rows=(("A", 24), ("B", 18))), head=1, include_expected=True)
    assert rec["got_head"] == {"columns": ["customer_id", "order_count"], "rows": [["A", 24]]}
    assert rec["expected"]["rows"] == [["A", 12], ["B", 9]]


# --- 요약 ---
def recs(spec):
    out = []
    for label, n, *rest in spec:
        trap, level = (rest + ["none", "L1"])[:2]
        out += [{"label": label, "trap": trap, "level": level}] * n
    return out


DESIGN = recs([("correct", 12), ("correct_approx", 1), ("extra_columns", 1),
               ("silent_wrong", 3), ("error", 1), ("skipped_unverified", 2)])


def test_summary_matches_design_example():
    s = _summary(DESIGN)
    assert (s["total"], s["scored"], s["skipped_unverified"]) == (20, 18, 2)
    assert (s["correct"], s["silent_wrong"], s["error"]) == (12, 3, 1)
    assert s["accuracy"] == 0.667


def test_statuses_not_in_denominator():
    s = _summary(recs([("correct", 1), ("missing_prediction", 5), ("unscorable", 4)]))
    assert s["scored"] == 1 and s["accuracy"] == 1.0
    assert (s["missing_prediction"], s["unscorable"]) == (5, 4)


def test_no_scored_accuracy_none():
    assert _summary(recs([("skipped_unverified", 3)]))["accuracy"] is None
    assert _summary([])["accuracy"] is None


def test_all_labels_present_in_summary():
    s = _summary([])
    assert set(s) == {"total", "scored", "accuracy", "accuracy_with_approx", "correct", "correct_approx",
                      "extra_columns", "silent_wrong", "error", "skipped_unverified", "unscorable",
                      "missing_prediction"}


def test_group_by_trap_counts_scored_only():
    r = recs([("correct", 1, "dup_join"), ("silent_wrong", 3, "dup_join"),
              ("skipped_unverified", 2, "dup_join"), ("correct", 2, "none")])
    assert _group(r, "trap") == {"dup_join": {"total": 4, "correct": 1}, "none": {"total": 2, "correct": 2}}


def test_group_unknown_and_sorted():
    r = recs([("correct", 1, "none", "L4"), ("correct_approx", 1, "none", None), ("correct", 1, "none", "L1")])
    g = _group(r, "level")
    assert list(g) == ["L1", "L4", "unknown"]
    assert g["unknown"] == {"total": 1, "correct": 0}


# --- score() 본체 ---
TODAY = date(2026, 11, 15)


def golden(*items, snapshot="2026-11-14"):
    return Golden("mysql", snapshot, list(items))


def preds(*items, dialect=None):
    return Predictions("prompt-v2", dialect, list(items))


def ids(n, **kw):
    return [G(id=f"q{i}", **kw) for i in range(1, n + 1)]


def run(g, p, **kw):
    return score(g, p, today=kw.pop("today", TODAY), **kw)


def test_report_top_level_keys():
    rep = run(golden(G()), preds(P()), golden_path="golden.yaml", preds_path="p.yaml")
    assert list(rep) == ["schema_version", "run", "summary", "by_trap", "by_level",
                         "regressions", "improvements", "warnings", "items"]
    assert rep["run"]["tool_version"] == __version__
    assert (rep["run"]["golden"], rep["run"]["run_name"], rep["run"]["dialect"]) == ("golden.yaml", "prompt-v2", "mysql")
    assert rep["summary"]["accuracy"] == 1.0 and rep["warnings"] == []


def test_duplicate_prediction_uses_first():
    first = P()
    second = P(rows=(("A", 99), ("B", 99)))
    assert run(golden(G()), preds(first, second))["items"][0]["label"] == "correct"


def test_baseline_regressions_and_improvements():
    g = golden(G(id="a"), G(id="b"), G(id="c", verified=False))
    base = {"items": [{"id": "a", "label": "correct"}, {"id": "b", "label": "silent_wrong"},
                      {"id": "c", "label": "correct"}]}
    p = preds(PredItem("a", Result(EXP.columns, [("A", 24), ("B", 18)])),
              PredItem("b", Result(EXP.columns, list(EXP.rows))),
              PredItem("c", Result(EXP.columns, list(EXP.rows))))
    rep = run(g, p, baseline=base)
    assert rep["regressions"] == ["a"] and rep["improvements"] == ["b"]


def wrong(i):
    return PredItem(f"q{i}", Result(EXP.columns, [("A", 0), ("B", 0)]))


def all_correct_baseline(n):
    return {"items": [{"id": f"q{i}", "label": "correct"} for i in range(1, n + 1)]}


@pytest.mark.parametrize("n_items,n_wrong,warn", [(10, 2, False), (10, 3, True), (50, 9, False), (50, 10, True)])
def test_mass_failure_threshold(n_items, n_wrong, warn):
    p = [wrong(i) if i <= n_wrong else PredItem(f"q{i}", Result(EXP.columns, list(EXP.rows)))
         for i in range(1, n_items + 1)]
    rep = run(golden(*ids(n_items)), preds(*p), baseline=all_correct_baseline(n_items))
    assert len(rep["regressions"]) == n_wrong
    assert any("한꺼번에" in w for w in rep["warnings"]) is warn


def test_stale_snapshot_warning():
    rep = run(golden(G(), snapshot="2026-10-15"), preds(P()))
    assert rep["warnings"] == ["snapshot이 31일 지남: 정답 다시 뽑기 권장"]


def test_unknown_prediction_id_warning():
    rep = run(golden(G()), preds(P(), PredItem("q07", error="x")))
    assert rep["warnings"] == ["골든셋에 없는 예측 id 1개는 채점하지 않음 (check로 확인)"]


def test_report_is_json_serializable_with_values():
    it = G(expected=Result(["d", "amt"], [(date(2018, 1, 5), Decimal("10.50"))]))
    p = PredItem("q1", Result(["d", "amt"], [(date(2018, 1, 5), Decimal("10.5"))]))
    rep = run(golden(it), preds(p), head=5, include_expected=True)
    assert rep["items"][0]["label"] == "correct"
    text = json.dumps(rep, ensure_ascii=False)
    assert '"2018-01-05"' in text and "10.5" in text


def test_default_tolerance_is_relative_0_1_percent():
    rep = run(golden(G()), preds(P()))
    assert rep["run"]["tolerance"] == 0.001


def test_empty_ok_passed_to_compare():
    it = G(expected=Result(["order_id"], []), empty_ok=True)
    rec = S(it, P(rows=(), cols=("order_id", "order_status")))
    assert rec["label"] == "correct" and rec["hints"] == ["필요 없는 컬럼 포함: order_status"]


def _one(label):
    return {"id": "A", "label": label, "trap": "none", "level": "L1"}


def test_report4_approx_not_regression():
    rec = _one("correct_approx")
    regs, imps = _baseline_diff([rec], {"items": [_one("correct")]})
    assert regs == [] and imps == []
    s = _summary([rec])
    assert s["accuracy"] == 0.0 and s["accuracy_with_approx"] == 1.0


def test_correct_to_silent_wrong_still_regression():
    regs, _ = _baseline_diff([_one("silent_wrong")], {"items": [_one("correct_approx")]})
    assert regs == ["A"]

