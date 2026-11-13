import math
from datetime import date
from decimal import Decimal

import pytest

from sqlverdict.compare import _project, cell_match, compare, match_columns, sort_key


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
    assert cell_match(152340.3333, 152340.33, 0.01) == "approx"


def test_tolerance_boundary():
    assert cell_match(100.0, 100.01, 0.01) == "approx"
    assert cell_match(100.0, 100.02, 0.01) is None


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
    assert cell_match(12, 24, 0.01) is None


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


def test_position_cannot_reuse_name_matched_column():
    m, by = match_columns(["a", "b"], ["b", "x"], ["a", "b"])
    assert m == {"a": None, "b": 0} and by == "position"


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
