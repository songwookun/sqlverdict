import math
import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from sqlverdict.compare import _project, cell_match, compare, match_columns, sort_key, to_result


def test_null_equals_null():
    assert cell_match(None, None, 0.01) == "strict"


@pytest.mark.parametrize("other", [0, "", 0.0])
def test_null_differs_from_zero_and_empty(other):
    assert cell_match(None, other, 0.01) is None
    assert cell_match(other, None, 0.01) is None


def test_int_float_equal():
    assert cell_match(3, 3.0, 0.01) == "strict"


def test_float_noise_is_strict():
    assert cell_match(0.1 + 0.2, 0.3, 0) == "strict"


def test_rounding_difference_is_approx():
    assert cell_match(152340.3333, 152340.33, 0.001) == "approx"


def test_tolerance_boundary_is_relative():
    assert cell_match(1000, 1001, 0.001) == "approx"
    assert cell_match(1000, 1001.1, 0.001) is None


# D2: 상대 오차라 작은 비율 값에 너그럽지 않음
def test_small_ratio_13_percent_off_is_wrong():
    assert cell_match(0.053, 0.060, 0.001) is None


def test_large_amount_small_relative_diff_is_approx():
    assert cell_match(100_000_000, 100_050_000, 0.001) == "approx"


def test_zero_expected_has_no_room():
    assert cell_match(0, 0.0001, 0.001) is None


def test_tolerance_zero_disables_approx():
    assert cell_match(152340.3333, 152340.33, 0) is None


def test_large_amount_strict_is_tight():
    # 1억 원에서 1원 차이도 엄격하게는 다름 (D1)
    assert cell_match(100_000_000, 100_000_001, 0) is None
    assert cell_match(100_000_000, 100_000_000.05, 0) == "strict"


def test_sum_noise_is_strict():
    assert cell_match(sum([0.1] * 10), 1.0, 0) == "strict"


def test_number_vs_string_differs():
    assert cell_match(3, "3", 0.01) is None


def test_string_case_and_space_sensitive():
    assert cell_match("Seoul", "Seoul", 0) == "strict"
    assert cell_match("Seoul", "seoul", 0) is None
    assert cell_match("Seoul", "Seoul ", 0) is None


def test_double_is_wrong():
    assert cell_match(12, 24, 0.001) is None


def test_nan_never_matches():
    assert cell_match(math.nan, math.nan, 0.01) is None


# --- 컬럼 짝 맞추기 ---
def test_match_by_name_even_if_reordered():
    m, by = match_columns(["id", "cnt"], ["cnt", "id"], ["id", "cnt"])
    assert m == {"id": 1, "cnt": 0} and by == "name"


def test_match_ignores_name_case():
    m, by = match_columns(["order_count"], ["ORDER_COUNT"], ["order_count"])
    assert m == {"order_count": 0} and by == "name"


def test_fallback_to_position():
    m, by = match_columns(["customer_id", "order_count"], ["customer_id", "cnt"],
                          ["customer_id", "order_count"])
    assert m == {"customer_id": 0, "order_count": 1} and by == "position"


def test_leftover_columns_pair_in_order():
    m, by = match_columns(["a", "b"], ["b", "x"], ["a", "b"])
    assert m == {"a": 1, "b": 0} and by == "position"


def test_missing_column_is_none():
    m, _ = match_columns(["id", "cnt"], ["id"], ["id", "cnt"])
    assert m == {"id": 0, "cnt": None}


def test_compare_columns_subset():
    m, by = match_columns(["id", "name", "cnt"], ["id", "cnt"], ["id", "cnt"])
    assert m == {"id": 0, "cnt": 1} and by == "name"


# --- 행 정렬 준비 ---
def test_sort_mixed_types_no_error():
    rows = [("b",), (None,), (3,), ("a",), (1.5,)]
    assert sorted(rows, key=sort_key) == [(None,), (1.5,), (3,), ("a",), ("b",)]


def test_sort_numbers_by_value_not_text():
    assert sorted([(10,), (9,)], key=sort_key) == [(9,), (10,)]


def test_sort_int_and_float_together():
    assert sorted([(3,), (2.5,)], key=sort_key) == [(2.5,), (3,)]


def test_project_reorders_to_expected():
    assert _project([(5, "A"), (3, "B")], [1, 0]) == [("A", 5), ("B", 3)]


# --- compare() 블록 1: 입력 정리 ---
def test_compare_requires_dialect():
    with pytest.raises(ValueError, match="dialect"):
        compare({"columns": ["a"], "rows": [[1]]}, {"columns": ["a"], "rows": [[1]]})


def test_missing_column_is_silent_wrong():
    v = compare({"columns": ["id", "cnt"], "rows": [["A", 12]]},
                {"columns": ["id"], "rows": [["A"]]}, dialect="mysql")
    assert v.label == "silent_wrong"
    assert v.detail["missing_columns"] == ["cnt"]
    assert v.detail["expected_rows"] == 1 and v.detail["got_rows"] == 1


# --- compare() 블록 2: 판정 ---
def R(columns, rows):
    return {"columns": columns, "rows": rows}


TOP = R(["customer_id", "order_count"], [["A", 12], ["B", 9], ["C", 7]])


def test_correct_with_different_row_order():
    got = R(["customer_id", "order_count"], [["C", 7], ["A", 12], ["B", 9]])
    assert compare(TOP, got, dialect="mysql").label == "correct"


def test_ordered_requires_same_order():
    got = R(["customer_id", "order_count"], [["C", 7], ["A", 12], ["B", 9]])
    v = compare(TOP, got, dialect="mysql", ordered=True)
    assert v.label == "silent_wrong"
    assert v.detail["differing_columns"] == ["customer_id", "order_count"]


def test_dup_join_doubles_values():
    got = R(["customer_id", "order_count"], [["A", 24], ["B", 18], ["C", 14]])
    v = compare(TOP, got, dialect="mysql")
    assert v.label == "silent_wrong" and v.detail["differing_columns"] == ["order_count"]
    assert v.detail["ratio"] == 2.0


def test_row_count_differs():
    got = R(["customer_id", "order_count"], [["A", 12], ["A", 12], ["B", 9], ["C", 7]])
    v = compare(TOP, got, dialect="mysql")
    assert v.label == "silent_wrong"
    assert (v.detail["expected_rows"], v.detail["got_rows"]) == (3, 4)


def test_correct_approx():
    v = compare(R(["avg"], [[152340.3333]]), R(["avg"], [[152340.33]]), dialect="sqlite")
    assert v.label == "correct_approx" and v.detail["approx"] is True


def test_tolerance_zero_makes_it_wrong():
    v = compare(R(["avg"], [[152340.3333]]), R(["avg"], [[152340.33]]),
                dialect="sqlite", tolerance=0)
    assert v.label == "silent_wrong"


def test_extra_columns():
    got = R(["customer_id", "order_count", "name"],
            [["A", 12, "x"], ["B", 9, "y"], ["C", 7, "z"]])
    v = compare(TOP, got, dialect="mysql")
    assert v.label == "extra_columns" and v.detail["extra_columns"] == ["name"]


def test_extra_columns_allowed():
    got = R(["customer_id", "order_count", "name"],
            [["A", 12, "x"], ["B", 9, "y"], ["C", 7, "z"]])
    assert compare(TOP, got, dialect="mysql", allow_extra_columns=True).label == "correct"


def test_wrong_values_beat_extra_columns():
    got = R(["customer_id", "order_count", "name"],
            [["A", 24, "x"], ["B", 18, "y"], ["C", 14, "z"]])
    assert compare(TOP, got, dialect="mysql").label == "silent_wrong"


def test_renamed_column_by_position():
    got = R(["customer_id", "cnt"], [["A", 12], ["B", 9], ["C", 7]])
    v = compare(TOP, got, dialect="mysql")
    assert v.label == "correct"
    assert v.detail["matched_by"] == "position"
    assert v.detail["column_map"] == {"order_count": "cnt"}


def test_compare_columns_subset_not_extra():
    exp = R(["customer_id", "name", "order_count"], [["A", "x", 12]])
    got = R(["customer_id", "order_count"], [["A", 12]])
    v = compare(exp, got, dialect="mysql", compare_columns=["customer_id", "order_count"])
    assert v.label == "correct"


def test_migration_mysql_to_postgresql():
    exp = R(["active", "amount", "day"], [[1, Decimal("10.50"), date(2018, 1, 5)]])
    got = R(["active", "amount", "day"], [[True, Decimal("10.5"), date(2018, 1, 5)]])
    v = compare(exp, got, expected_dialect="mysql", got_dialect="postgresql")
    assert v.label == "correct"


def test_migration_to_oracle_empty_string_is_caught():
    exp = R(["memo"], [[""]])
    got = R(["memo"], [[""]])
    v = compare(exp, got, expected_dialect="mysql", got_dialect="oracle")
    assert v.label == "silent_wrong"


def test_empty_results_match():
    assert compare(R(["a"], []), R(["a"], []), dialect="sqlite").label == "correct"


def test_null_vs_zero_count():
    v = compare(R(["n"], [[None]]), R(["n"], [[0]]), dialect="sqlite")
    assert v.label == "silent_wrong"


# --- 배수 ---
def test_no_ratio_when_inconsistent():
    got = R(["customer_id", "order_count"], [["A", 24], ["B", 9], ["C", 7]])
    assert "ratio" not in compare(TOP, got, dialect="mysql").detail


def test_no_ratio_when_expected_zero():
    v = compare(R(["n"], [[0], [5]]), R(["n"], [[0], [10]]), dialect="sqlite")
    assert v.label == "silent_wrong" and "ratio" not in v.detail


def test_no_ratio_for_string_column():
    v = compare(R(["c"], [["A"]]), R(["c"], [["B"]]), dialect="sqlite")
    assert "ratio" not in v.detail


def test_ratio_found_on_second_differing_column():
    exp = R(["name", "total"], [["A", 100], ["B", 50]])
    got = R(["name", "total"], [["a", 300], ["b", 150]])
    v = compare(exp, got, dialect="sqlite", ordered=True)
    assert v.detail["differing_columns"] == ["name", "total"] and v.detail["ratio"] == 3.0


def _cur(sql, row_factory=None):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = row_factory
    cur = conn.cursor()
    cur.execute(sql)
    return cur


def test_to_result_from_cursor():
    r = to_result(_cur("SELECT 1 AS n, 'A' AS c UNION ALL SELECT 2, 'B'"))
    assert r.columns == ["n", "c"] and r.rows == [(1, "A"), (2, "B")]
    assert compare(r, {"columns": ["n", "c"], "rows": [[2, "B"], [1, "A"]]}, dialect="sqlite").label == "correct"


def test_to_result_dict_rows_use_values_not_keys():
    as_dict = lambda cur, row: {d[0]: v for d, v in zip(cur.description, row)}  # noqa: E731
    r = to_result(_cur("SELECT 1 AS n, 'A' AS c", as_dict))
    assert r.rows == [(1, "A")]


def test_to_result_without_select_raises():
    with pytest.raises(ValueError, match="SELECT"):
        to_result(sqlite3.connect(":memory:").cursor())


def test_compare_fills_hints():
    exp = {"columns": ["n"], "rows": [[12]]}
    v = compare(exp, {"columns": ["n"], "rows": [[24]]}, dialect="mysql")
    assert v.hints == ["값이 정확히 2배: 중복 조인·필터 누락 의심"]
    assert compare(exp, exp, dialect="mysql").hints == []


def test_compare_pred_sql_hint():
    r = {"columns": ["n"], "rows": [[1]]}
    v = compare(r, r, dialect="mysql", pred_sql="select * from t")
    assert v.label == "correct" and v.hints == ["SELECT * 사용: 필요한 컬럼만 고르세요"]


def test_report1_name_and_leftover_mix_is_correct():
    exp = {"columns": ["seller_state", "n"], "rows": [["SP", 1849], ["PR", 349]]}
    got = {"columns": ["cnt", "seller_state"], "rows": [[1849, "SP"], [349, "PR"]]}
    v = compare(exp, got, dialect="sqlite", ordered=True)
    assert v.label == "correct" and v.detail["column_map"] == {"n": "cnt"}
    assert any("위치로 비교함" in h for h in v.hints) and not any("없음" in h for h in v.hints)


EMPTY_EXP = {"columns": ["order_id"], "rows": []}
EMPTY_GOT = {"columns": ["order_id", "order_status"], "rows": []}


def test_report3_empty_ok_both_empty_is_correct():
    v = compare(EMPTY_EXP, EMPTY_GOT, dialect="sqlite", empty_ok=True)
    assert v.label == "correct" and v.detail["empty_ok"] is True
    assert v.hints == ["필요 없는 컬럼 포함: order_status"]


def test_without_empty_ok_extra_columns_stays_strict():
    assert compare(EMPTY_EXP, EMPTY_GOT, dialect="sqlite").label == "extra_columns"


def test_empty_ok_but_prediction_has_rows():
    got = {"columns": ["order_id"], "rows": [[1]]}
    assert compare(EMPTY_EXP, got, dialect="sqlite", empty_ok=True).label == "silent_wrong"

