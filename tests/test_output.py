import json

from sqlverdict.output.json_out import to_json
from sqlverdict.output.table import _cut, _info, _pad, _table, _width, render_table


def test_json_keeps_korean_and_roundtrips():
    rep = {"items": [{"question": "2018년 고객별 주문 건수", "label": "correct"}]}
    text = to_json(rep)
    assert "2018년 고객별" in text and "\\u" not in text
    assert json.loads(text) == rep


def test_width_counts_wide_chars_as_two():
    assert _width("abc") == 3
    assert _width("한글") == 4
    assert _width("q1 상위5") == 3 + 2 + 2 + 1


def test_cut_by_width_with_ellipsis():
    assert _cut("short", 10) == "short"
    assert _cut("가나다라마바", 7) == "가나다…"
    assert _width(_cut("가나다라마바", 7)) <= 7


def test_cut_collapses_whitespace():
    assert _cut("첫 줄\n  둘째   줄", 30) == "첫 줄 둘째 줄"


def test_exact_fit_is_cut_to_leave_room():
    assert _cut("abcde", 5) == "abcd…"
    assert _cut("abcd", 5) == "abcd"


def test_pad():
    assert _pad("한", 4) == "한  "
    assert _pad("12", 4, right=True) == "  12"


def test_table_right_align():
    out = _table(["k", "n"], [["a", 4], ["b", 12]], right={1}).splitlines()
    assert out[2:] == ["a   4", "b  12"]


def test_table_aligns_with_korean():
    out = _table(["id", "question"], [["q1", "한글 질문"], ["q22", "en"]]).splitlines()
    assert out[0] == "id   question"
    assert out[1] == "---  ---------"
    assert out[2] == "q1   한글 질문"
    assert out[3] == "q22  en"


# --- 터미널 보고서 ---
def item(id, label, **kw):
    base = {"id": id, "question": "2018년 고객별 주문 건수 상위 5명은?", "level": "L4",
            "trap": "dup_join", "label": label, "diff": {}, "hints": []}
    return {**base, **kw}


def report(**kw):
    base = {
        "run": {"run_name": "prompt-v2", "dialect": "mysql", "pred_dialect": None,
                "snapshot": "2026-11-13", "tool_version": "0.1.0"},
        "summary": {"total": 20, "scored": 18, "accuracy": 0.667, "correct": 12, "correct_approx": 1,
                    "extra_columns": 1, "silent_wrong": 3, "error": 1,
                    "skipped_unverified": 2, "unscorable": 0, "missing_prediction": 0},
        "by_trap": {"dup_join": {"total": 4, "correct": 1}},
        "by_level": {"L4": {"total": 5, "correct": 2}},
        "regressions": [], "improvements": [], "warnings": [],
        "items": [item("q001", "correct"), item("q002", "skipped_unverified"),
                  item("q007", "silent_wrong", hints=["값이 정확히 2배: 중복 조인·필터 누락 의심"])],
    }
    return {**base, **kw}


def test_render_design_example():
    out = render_table(report())
    assert out.splitlines()[0] == "sqlverdict 0.1.0 · prompt-v2 · mysql · snapshot 2026-11-13"
    assert "정확도 66.7%  (correct 12 / 채점 18 / 전체 20)" in out
    assert "판정  correct 12 · correct_approx 1 · extra_columns 1 · silent_wrong 3 · error 1" in out
    assert "제외  skipped_unverified 2 · unscorable 0 · missing_prediction 0" in out
    assert "dup_join     4     1   25.0%" in out


def test_only_items_to_fix_are_listed():
    out = render_table(report())
    assert "q007" in out and "중복 조인·필터 누락 의심" in out
    assert "q001" not in out and "q002" not in out


def test_warnings_on_top():
    out = render_table(report(warnings=["snapshot이 31일 지남: 정답 다시 뽑기 권장"]))
    blocks = out.split("\n\n")
    assert blocks[1] == "! snapshot이 31일 지남: 정답 다시 뽑기 권장"


def test_migration_and_baseline_lines():
    r = report(regressions=["q003"], improvements=["q010", "q011"])
    r["run"] = {**r["run"], "pred_dialect": "postgresql"}
    out = render_table(r)
    assert "mysql → postgresql" in out.splitlines()[0]
    assert "새로 틀림  q003" in out and "새로 맞음  q010, q011" in out


def test_info_priority():
    assert _info(item("a", "unscorable", reason="형식", error="e", hints=["h"])) == "형식"
    assert _info(item("a", "error", error="Unknown column")) == "실행 실패: Unknown column"
    assert _info(item("a", "silent_wrong", hints=["h1", "h2"])) == "h1 / h2"


def test_no_scored_shows_dash():
    r = report(by_trap={}, by_level={}, items=[])
    r["summary"] = {**r["summary"], "accuracy": None}
    assert "정확도 -  (" in render_table(r)


def test_values_never_in_table():
    r = report(items=[item("q9", "silent_wrong", got_head={"columns": ["name"], "rows": [["홍길동"]]},
                           expected={"columns": ["name"], "rows": [["김철수"]]})])
    out = render_table(r)
    assert "홍길동" not in out and "김철수" not in out


def test_end_to_end_with_score():
    from sqlverdict.model import Golden, GoldenItem, PredItem, Predictions, Result
    from sqlverdict.score import score
    exp = Result(["id", "n"], [("A", 12)])
    g = Golden("mysql", "2026-11-14", [GoldenItem("q1", "질문", exp, level="L4", trap="dup_join",
                                                    why="w", verified=True)])
    p = Predictions("v2", None, [PredItem("q1", Result(["id", "n"], [("A", 24)]))])
    out = render_table(score(g, p, today=__import__("datetime").date(2026, 11, 15)))
    assert "정확도 0.0%" in out and "값이 정확히 2배" in out
