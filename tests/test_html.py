import re

from datetime import date

from sqlverdict.output.html_out import _page, _table, esc, render_html

XSS = '<script>alert("x")</script>'


def test_esc_special_chars():
    assert esc(XSS) == "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;"
    assert esc("a & b 'c'") == "a &amp; b &#x27;c&#x27;"


def test_esc_none_and_numbers():
    assert esc(None) == "" and esc(0) == "0" and esc(0.667) == "0.667"


def test_table_cells_escaped():
    out = _table(["<h>"], [[XSS], [None]])
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<th>&lt;h&gt;</th>" in out and "<td></td>" in out


def test_row_class_attribute_escaped():
    out = _table(["a"], [["1"]], row_class=['x" onmouseover="alert(1)'])
    assert 'onmouseover="' not in out
    assert 'class="x&quot; onmouseover=&quot;alert(1)"' in out


def test_page_has_csp_and_escapes_title():
    out = _page(XSS, "<p>ok</p>")
    assert "Content-Security-Policy" in out and "default-src 'none'" in out
    assert "<title>&lt;script&gt;" in out and "<p>ok</p>" in out
    assert out.startswith("<!doctype html>")


def test_no_external_resources():
    out = _page("t", _table(["a"], [["b"]]))
    assert not re.search(r"https?://|src=|<link|<script", out, re.IGNORECASE)


# --- render_html ---
def item(id, label, **kw):
    base = {"id": id, "question": "2018년 고객별 주문 건수 상위 5명은?", "level": "L4",
            "trap": "dup_join", "label": label, "diff": {}, "hints": []}
    return {**base, **kw}


def report(**kw):
    base = {
        "run": {"run_name": "prompt-v2", "dialect": "mysql", "pred_dialect": None, "snapshot": "2026-11-13",
                "tolerance": 0.001, "tool_version": "0.1.0"},
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


def test_header_accuracy_and_tolerance():
    out = render_html(report())
    assert "66.7%" in out and "tolerance 0.1%" in out and "prompt-v2 · mysql" in out
    assert "<td>dup_join</td><td>4</td><td>1</td><td>25.0%</td>" in out


def test_warnings_above_accuracy():
    out = render_html(report(warnings=["snapshot이 31일 지남"]))
    assert out.index('class="warn"') < out.index('class="big"')


def test_items_to_fix_with_label_class():
    out = render_html(report())
    assert '<tr class="silent_wrong"><td>q007</td>' in out
    assert "q001" not in out and "q002" not in out
    assert "2018년 고객별 주문 건수 상위 5명은?" in out  # 자르지 않음


def test_values_hidden_by_default():
    out = render_html(report(items=[item("q9", "silent_wrong")]))
    assert "<details>" not in out and "결과 값" not in out


def test_values_shown_in_details_when_included():
    r = report(items=[item("q9", "silent_wrong", got_head={"columns": ["name"], "rows": [["홍길동"]]},
                           expected={"columns": ["name"], "rows": [["김철수"]]})])
    out = render_html(r)
    d = out[out.index("<details>"):]
    assert "홍길동" in d and "김철수" in d


def test_xss_everywhere():
    r = report(warnings=[XSS], regressions=[XSS], improvements=[XSS],
               by_trap={XSS: {"total": 1, "correct": 0}},
               items=[item(XSS, "unscorable", question=XSS, reason=XSS, trap=XSS, level=XSS),
                      item("e", "error", error=XSS),
                      item("v", "silent_wrong", hints=[XSS],
                           got_head={"columns": [XSS], "rows": [[XSS]]})])
    r["run"] = {**r["run"], "run_name": XSS, "snapshot": XSS, "pred_dialect": XSS}
    out = render_html(r)
    assert "<script" not in out.lower()
    assert re.search(r"<[a-z]+[^>]*\son\w+=", out) is None


def test_end_to_end_with_score():
    from sqlverdict.model import Golden, GoldenItem, PredItem, Predictions, Result
    from sqlverdict.score import score
    exp = Result(["id", "n"], [("A", 12)])
    g = Golden("mysql", "2026-11-15", [GoldenItem("q1", "질문", exp, level="L4", trap="dup_join",
                                                    why="w", verified=True)])
    p = Predictions("v2", None, [PredItem("q1", Result(["id", "n"], [("A", 24)]))])
    out = render_html(score(g, p, today=date(2026, 11, 16)))
    assert out.startswith("<!doctype html>") and out.endswith("</html>")
    assert "0.0%" in out and "값이 정확히 2배" in out
