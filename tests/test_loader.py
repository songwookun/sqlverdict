import pytest
import yaml

from sqlverdict.loader import (
    InputError, _dialect, _golden_item, _pred_item, _read, _result, load_golden, load_predictions,
)


def write(tmp_path, text):
    p = tmp_path / "f.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_norway_stays_string(tmp_path):
    data = _read(write(tmp_path, "items:\n  - rows: [[NO, yes, on, off, Y]]\n"))
    assert data["items"][0]["rows"] == [["NO", "yes", "on", "off", "Y"]]


def test_true_false_are_bool(tmp_path):
    data = _read(write(tmp_path, "items:\n  - a: true\n    b: False\n"))
    assert data["items"][0] == {"a": True, "b": False}


def test_safe_loader_original_untouched():
    assert yaml.safe_load("x: yes") == {"x": True}


def test_python_tag_rejected(tmp_path):
    p = write(tmp_path, "items: !!python/object/apply:os.system ['echo hi']\n")
    with pytest.raises(InputError, match="YAML"):
        _read(p)


def test_missing_file(tmp_path):
    with pytest.raises(InputError, match="파일이 없습니다"):
        _read(tmp_path / "nope.yaml")


def test_broken_yaml(tmp_path):
    with pytest.raises(InputError, match="YAML 형식 오류"):
        _read(write(tmp_path, "items: [\n"))


def test_items_required(tmp_path):
    with pytest.raises(InputError, match="items"):
        _read(write(tmp_path, "dialect: mysql\n"))


def test_dialect_typo():
    with pytest.raises(InputError, match="dialect"):
        _dialect("postgres", "g.yaml", required=True)


def test_dialect_optional():
    assert _dialect(None, "p.yaml", required=False) is None
    with pytest.raises(InputError):
        _dialect(None, "g.yaml", required=True)


def test_result_ok():
    r, problem = _result({"columns": ["a", "b"], "rows": [[1, 2]]}, unique_columns=True)
    assert problem is None and r.rows == [(1, 2)]


def test_result_shape_missing():
    assert _result({"columns": ["a"]}, True) == (None, "columns와 rows 목록이 필요합니다")
    assert _result(None, True)[0] is None


def test_result_row_length():
    _, problem = _result({"columns": ["a", "b"], "rows": [[1, 2], [3]]}, True)
    assert problem == "2번째 행의 값 개수가 컬럼 수(2)와 다릅니다"


def test_duplicate_columns_only_blocked_for_expected():
    raw = {"columns": ["id", "ID"], "rows": [[1, 2]]}
    assert _result(raw, unique_columns=True)[1] == "컬럼 이름이 중복됩니다"
    assert _result(raw, unique_columns=False)[1] is None


# --- 골든셋 문항 ---
EXP = {"columns": ["customer_id", "order_count"], "rows": [["A", 12]]}


def item(**kw):
    return {"id": "q1", "question": "질문", "expected": EXP, **kw}


def test_golden_item_ok():
    g = _golden_item(item(level="L4", trap="dup_join", why="w", verified=True, ordered=True,
                          tolerance=0, compare_columns=["order_count"]), 1)
    assert g.problem is None
    assert (g.id, g.level, g.verified, g.ordered, g.tolerance) == ("q1", "L4", True, True, 0)
    assert g.expected.columns == ["customer_id", "order_count"]
    assert g.compare_columns == ["order_count"]


def test_defaults_are_safe():
    g = _golden_item(item(), 1)
    assert g.verified is False and g.ordered is False and g.allow_extra_columns is False


def test_not_a_dict():
    g = _golden_item(["q1"], 3)
    assert g.id == "#3" and "형식" in g.problem


def test_missing_and_numeric_id():
    assert _golden_item({"expected": EXP}, 2).id == "#2"
    assert _golden_item({"id": 7, "expected": EXP}, 1).id == "7"


def test_missing_question_is_none():
    assert _golden_item({"id": "q1", "expected": EXP}, 1).question is None


def test_typo_field_unscorable():
    g = _golden_item(item(orderd=True), 1)
    assert g.problem == "알 수 없는 필드: orderd"


def test_bool_field_rejects_yes_string():
    assert _golden_item(item(ordered="yes"), 1).problem == "ordered는 true 또는 false여야 합니다"


@pytest.mark.parametrize("tol", [-1, True, "0.1"])
def test_bad_tolerance(tol):
    assert _golden_item(item(tolerance=tol), 1).problem == "tolerance는 0 이상의 숫자여야 합니다"


def test_compare_columns_not_in_expected():
    g = _golden_item(item(compare_columns=["cnt"]), 1)
    assert g.problem == "compare_columns에 정답 표에 없는 컬럼이 있습니다"


def test_compare_columns_empty():
    assert "비어 있지 않은" in _golden_item(item(compare_columns=[]), 1).problem


def test_problems_are_collected():
    g = _golden_item({"id": "q1", "expected": {"columns": ["a"]}, "orderd": 1, "empty_ok": "no"}, 1)
    assert g.problem.count(";") == 2


def test_text_fields_become_str():
    g = _golden_item(item(question=2018, level=4), 1)
    assert g.question == "2018" and g.level == "4"


# --- 예측 문항 · 파일 전체 ---
GOLDEN_YAML = """\
dialect: mysql
snapshot: "2026-11-13"
items:
  - id: q007
    question: "2018년 고객별 주문 건수 상위 5명은?"
    expected:
      columns: [customer_id, order_count]
      rows: [["A", 12], ["B", 9], ["C", 7], ["D", 6], ["E", 5]]
    ordered: true
    compare_columns: [customer_id, order_count]
    allow_extra_columns: false
    tolerance: 0.01
    level: L4
    trap: dup_join
    why: "orders와 order_items를 조인하면 주문이 상품 수만큼 늘어남"
    empty_ok: false
    verified: false
    gold_sql: |
      SELECT customer_id, COUNT(*) AS order_count FROM orders
"""

PRED_YAML = """\
run_name: "prompt-v2"
dialect: postgresql
items:
  - id: q007
    pred_sql: "SELECT ..."
    result:
      columns: [customer_id, cnt]
      rows: [["A", 24], ["B", 18]]
  - id: q008
    error: "Unknown column 'order_dt'"
"""


def test_load_golden_design_example(tmp_path):
    g = load_golden(write(tmp_path, GOLDEN_YAML))
    assert (g.dialect, g.snapshot, len(g.items)) == ("mysql", "2026-11-13", 1)
    it = g.items[0]
    assert it.problem is None and it.ordered is True and it.trap == "dup_join"
    assert it.expected.rows[0] == ("A", 12)
    assert it.gold_sql.startswith("SELECT customer_id")


def test_load_predictions_design_example(tmp_path):
    p = load_predictions(write(tmp_path, PRED_YAML))
    assert (p.run_name, p.dialect) == ("prompt-v2", "postgresql")
    ok, err = p.items
    assert ok.problem is None and ok.result.columns == ["customer_id", "cnt"]
    assert err.problem is None and err.result is None and "order_dt" in err.error


def test_pred_needs_exactly_one_of_result_error():
    both = _pred_item({"id": "q1", "result": EXP, "error": "x"}, 1)
    none = _pred_item({"id": "q1"}, 1)
    assert both.problem == none.problem == "result와 error 중 정확히 하나가 필요합니다"


def test_pred_allows_duplicate_columns():
    p = _pred_item({"id": "q1", "result": {"columns": ["id", "id"], "rows": [[1, 2]]}}, 1)
    assert p.problem is None


def test_pred_typo_and_not_dict():
    assert _pred_item({"id": "q1", "error": "x", "reslt": {}}, 1).problem == "알 수 없는 필드: reslt"
    assert _pred_item("q1", 4).id == "#4"


def test_top_level_typo_is_file_error(tmp_path):
    with pytest.raises(InputError, match="dialet"):
        load_predictions(write(tmp_path, "dialet: postgresql\nitems: []\n"))


def test_unquoted_snapshot_becomes_string(tmp_path):
    g = load_golden(write(tmp_path, "dialect: sqlite\nsnapshot: 2026-11-13\nitems: []\n"))
    assert g.snapshot == "2026-11-13"


def test_golden_dialect_required(tmp_path):
    with pytest.raises(InputError, match="dialect"):
        load_golden(write(tmp_path, "items: []\n"))


def test_pred_dialect_optional(tmp_path):
    assert load_predictions(write(tmp_path, "items: []\n")).dialect is None


def test_one_bad_item_does_not_stop_file(tmp_path):
    text = "dialect: mysql\nitems:\n  - id: a\n    orderd: true\n  - id: b\n" \
           "    expected: {columns: [x], rows: [[1]]}\n"
    g = load_golden(write(tmp_path, text))
    assert g.items[0].problem and g.items[1].problem is None
