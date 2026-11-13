from sqlverdict import compare
from sqlverdict.hints import build_hints


def H(label, sql=None, **detail):
    return build_hints(label, detail, sql)


def test_rows_doubled():
    assert "행 수가 정확히 2배: 중복 조인 의심" in H("silent_wrong", expected_rows=5, got_rows=10)


def test_rows_not_multiple_no_hint():
    assert H("silent_wrong", expected_rows=5, got_rows=7) == []


def test_empty_result():
    assert any("비어 있음" in h for h in H("silent_wrong", expected_rows=5, got_rows=0))


def test_empty_expected_and_got_no_hint():
    assert H("correct", expected_rows=0, got_rows=0) == []


def test_value_ratio_up_and_down():
    assert H("silent_wrong", ratio=2.0) == ["값이 정확히 2배: 중복 조인 의심"]
    assert H("silent_wrong", ratio=0.5) == ["값이 정확히 0.5배: 필터 누락·기간 차이 의심"]


def test_missing_columns():
    assert H("silent_wrong", missing_columns=["cnt"]) == ["필요한 컬럼이 없음: cnt"]


def test_position_match():
    assert any("위치로 비교함" in h for h in H("correct", matched_by="position"))


def test_extra_columns():
    assert H("extra_columns", extra_columns=["name"]) == ["필요 없는 컬럼 포함: name"]


def test_select_star_variants():
    for sql in ["SELECT * FROM t", "select\n  * from t", "SELECT DISTINCT * FROM t"]:
        assert any("SELECT *" in h for h in H("correct", sql)), sql


def test_count_star_not_flagged():
    assert H("correct", "SELECT COUNT(*) FROM t") == []


def test_end_to_end_with_compare():
    exp = {"columns": ["id", "n"], "rows": [["A", 12], ["B", 9]]}
    got = {"columns": ["id", "n"], "rows": [["A", 24], ["B", 18]]}
    v = compare(exp, got, dialect="mysql")
    assert build_hints(v.label, v.detail) == ["값이 정확히 2배: 중복 조인 의심"]


def test_hints_never_contain_values():
    exp = {"columns": ["secret"], "rows": [["홍길동-010-1234"]]}
    got = {"columns": ["secret"], "rows": [["김철수-010-9999"]]}
    v = compare(exp, got, dialect="mysql")
    text = " ".join(build_hints(v.label, v.detail))
    assert "홍길동" not in text and "김철수" not in text
