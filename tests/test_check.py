from datetime import date

import pytest

from sqlverdict.check import _item_issues, _pred_issues, _set_issues, _text_issues, check
from sqlverdict.loader import load_golden, load_predictions
from sqlverdict.model import Golden, GoldenItem, PredItem, Predictions, Result

EXP = Result(["a"], [(1,)])


def G(**kw):
    base = dict(id="q1", question="질문", expected=EXP, level="L2", trap="none", verified=True)
    return GoldenItem(**{**base, **kw})


def msgs(it):
    return [(i.severity, i.message) for i in _item_issues(it)]


def test_clean_item_has_no_issues():
    assert _item_issues(G()) == []
    assert _item_issues(G(trap="dup_join", why="조인 시 행이 늘어남")) == []


def test_problem_is_error():
    (sev, m), = msgs(G(problem="알 수 없는 필드: orderd"))
    assert sev == "error" and "orderd" in m


def test_issue_carries_id():
    assert _item_issues(G(question=None))[0].id == "q1"


@pytest.mark.parametrize("field,value", [("question", None), ("question", ""),
                                         ("level", None), ("level", "L5"), ("level", "l4"),
                                         ("trap", None), ("trap", "dupjoin")])
def test_required_fields(field, value):
    (sev, _), = msgs(G(**{field: value}))
    assert sev == "error"


def test_trap_needs_why():
    assert msgs(G(trap="dup_join")) == [("error", "trap이 있으면 why가 필요합니다 (사람이 이것만 읽고 검증)")]


def test_bad_trap_does_not_also_ask_why():
    assert len(msgs(G(trap="dupjoin"))) == 1


def test_unverified_is_warn():
    (sev, m), = msgs(G(verified=False))
    assert sev == "warn" and "verified" in m


def test_empty_expected():
    assert msgs(G(expected=Result(["a"], [])))[0][0] == "warn"
    assert msgs(G(expected=Result(["a"], []), empty_ok=True)) == []


def test_broken_expected_no_duplicate_empty_warning():
    assert [s for s, _ in msgs(G(expected=None, problem="x"))] == ["error"]


# --- 문장 패턴 ---
def texts(**kw):
    return [i.message for i in _text_issues(G(**kw))]


def test_gold_sql_select_star():
    assert any("SELECT *" in m for m in texts(gold_sql="SELECT * FROM orders"))
    assert texts(gold_sql="SELECT COUNT(*) FROM orders") == []


@pytest.mark.parametrize("sql,fn", [
    ("SELECT * FROM t WHERE d > NOW()", "NOW"),
    ("SELECT id FROM t WHERE d = CURRENT_DATE", "CURRENT_DATE"),
    ("SELECT id FROM t WHERE d > date('now', '-30 day')", "now"),
    ("SELECT id FROM t ORDER BY RAND() LIMIT 1", "RAND"),
])
def test_volatile_functions(sql, fn):
    assert any(f"함수 {fn}:" in m for m in texts(gold_sql=sql))


def test_stable_sql_no_warning():
    assert texts(gold_sql="SELECT id FROM t WHERE d BETWEEN '2018-01-01' AND '2018-12-31'") == []


@pytest.mark.parametrize("q,word", [("최근 30일 매출은?", "최근"), ("이번달 주문 수", "이번달"),
                                    ("이번 달 주문 수", "이번 달"), ("작년 고객 수", "작년"),
                                    ("Sales this month?", "this month"), ("today's orders", "today")])
def test_open_period(q, word):
    (m,) = texts(question=q)
    assert f"'{word}'" in m


def test_closed_period_ok():
    assert texts(question="2018년 1월 고객별 주문 건수 상위 5명은?") == []


def test_currency_not_flagged():
    assert texts(question="Total sales by currency in 2018") == []


# --- 전체 검사 ---
TODAY = date(2026, 11, 14)


def golden(*items, snapshot="2026-11-13"):
    return Golden("mysql", snapshot, list(items))


def set_msgs(g):
    return [(i.severity, i.id, i.message) for i in _set_issues(g, TODAY)]


MIXED = (G(id="a", trap="dup_join", why="w", level="L1"), G(id="b", level="L4"))


def test_balanced_golden_clean():
    assert set_msgs(golden(*MIXED)) == []


def test_duplicate_id():
    assert ("error", "a", "id가 중복됩니다") in set_msgs(golden(*MIXED, G(id="a", level="L2")))


def test_empty_golden():
    assert set_msgs(golden()) == [("warn", None, "문항이 없습니다")]


def test_no_trap_items():
    assert any("함정 문항이 없습니다" in m for *_, m in set_msgs(golden(G(id="a", level="L1"), G(id="b", level="L4"))))


def test_single_level():
    out = set_msgs(golden(G(id="a", trap="dup_join", why="w", level="L1"), G(id="b", level="L1")))
    assert any("L1 하나뿐" in m for *_, m in out)


@pytest.mark.parametrize("snap,expect", [
    (None, "snapshot이 없습니다"), ("13/11/2026", "YYYY-MM-DD"),
    ("2026-10-15", None), ("2026-10-14", "31일 지났습니다"),
])
def test_snapshot(snap, expect):
    out = [m for *_, m in set_msgs(golden(*MIXED, snapshot=snap))]
    assert (out == []) if expect is None else any(expect in m for m in out)


def preds(*items):
    return Predictions("run", None, list(items))


def pred_msgs(g, p):
    return [(i.severity, i.id, i.message) for i in _pred_issues(g, p)]


R1 = Result(["a"], [(1,)])


def test_pred_pairing_clean():
    assert pred_msgs(golden(*MIXED), preds(PredItem("a", R1), PredItem("b", error="x"))) == []


def test_pred_duplicate_unknown_problem_missing():
    out = pred_msgs(golden(*MIXED), preds(PredItem("a", R1), PredItem("a", R1),
                                          PredItem("q07", R1), PredItem("#4", problem="형식")))
    assert ("error", "a", "예측 id가 중복됩니다") in out
    assert ("error", "q07", "골든셋에 없는 id입니다") in out
    assert ("error", "#4", "예측 형식 오류: 형식") in out
    assert ("warn", "b", "예측이 없습니다 (missing_prediction)") in out


def test_missing_prediction_in_golden_order():
    g = golden(G(id="z", trap="dup_join", why="w", level="L1"), G(id="a", level="L4"), G(id="m", level="L2"))
    assert [i for _, i, _ in pred_msgs(g, preds())] == ["z", "a", "m"]


def test_check_end_to_end(tmp_path):
    gp = tmp_path / "golden.yaml"
    gp.write_text("""\
dialect: mysql
snapshot: "2026-11-13"
items:
  - id: q007
    question: "2018년 고객별 주문 건수 상위 5명은?"
    expected: {columns: [customer_id, order_count], rows: [["A", 12]]}
    level: L4
    trap: dup_join
    why: "조인하면 주문이 상품 수만큼 늘어남"
    verified: true
    gold_sql: "SELECT customer_id, COUNT(*) AS order_count FROM orders"
  - id: q008
    question: "최근 30일 주문 수는?"
    expected: {columns: [n], rows: [[3]]}
    level: L1
    trap: none
    verified: false
    gold_sql: "SELECT * FROM orders WHERE d > NOW()"
""", encoding="utf-8")
    pp = tmp_path / "p.yaml"
    pp.write_text("items:\n  - id: q007\n    error: x\n  - id: q09\n    error: y\n", encoding="utf-8")
    out = check(load_golden(gp), load_predictions(pp), today=TODAY)
    assert [(i.severity, i.id) for i in out] == [
        ("warn", "q008"), ("warn", "q008"), ("warn", "q008"), ("warn", "q008"),
        ("error", "q09"), ("warn", "q008"),
    ]


def test_check_without_preds():
    assert check(golden(*MIXED), today=TODAY) == []
