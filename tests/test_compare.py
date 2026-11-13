import math

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
