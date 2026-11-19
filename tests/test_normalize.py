import math
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from sqlverdict.normalize import DIALECTS, _number, normalize_rows, normalize_value


def test_bool_becomes_int():
    assert _number(True) == 1 and type(_number(True)) is int
    assert _number(False) == 0 and type(_number(False)) is int


def test_decimal_integral_becomes_int():
    assert _number(Decimal("12")) == 12 and type(_number(Decimal("12"))) is int
    assert _number(Decimal("12.000")) == 12 and type(_number(Decimal("12.000"))) is int


def test_decimal_fraction_becomes_float():
    assert _number(Decimal("152340.3333")) == 152340.3333


def test_whole_float_becomes_int():
    assert _number(3.0) == 3 and type(_number(3.0)) is int


def test_others_untouched():
    assert _number(1.5) == 1.5
    assert _number("3") == "3"
    assert _number(None) is None


# --- 날짜 · NULL · 공개 함수 ---


def test_decimal_infinity_and_nan_do_not_crash():
    assert _number(Decimal("Infinity")) == math.inf
    assert _number(Decimal("NaN")) == _number(float("nan")) == "NaN"


def test_datetime_keeps_time():
    assert normalize_value(datetime(2018, 1, 5, 13, 4, 9), "mysql") == "2018-01-05 13:04:09"


def test_date_becomes_string():
    assert normalize_value(date(2018, 1, 5), "postgresql") == "2018-01-05"


def test_midnight_datetime_equals_date():               # D14: Oracle DATE
    assert normalize_value(datetime(2024, 1, 1), "oracle") == normalize_value(date(2024, 1, 1), "mysql") == "2024-01-01"


def test_fraction_seconds_kept():                       # D15
    assert normalize_value(datetime(2024, 1, 1, 12, 0, 0, 500000), "mysql") == "2024-01-01 12:00:00.5"
    assert normalize_value(datetime(2024, 1, 1, 12, 0, 0, 500000), "mysql") != normalize_value(datetime(2024, 1, 1, 12, 0, 0, 900000), "mysql")


def test_aware_datetime_to_utc():                       # D16
    kst = timezone(timedelta(hours=9))
    v = normalize_value(datetime(2024, 1, 1, 12, 0, tzinfo=kst), "postgresql")
    assert v == "2024-01-01 03:00:00+00:00"
    assert v == normalize_value(datetime(2024, 1, 1, 3, 0, tzinfo=timezone.utc), "postgresql")
    assert normalize_value(datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc), "postgresql") == "2024-01-01 00:00:00+00:00"
    assert v != normalize_value(datetime(2024, 1, 1, 3, 0), "oracle")


def test_time_and_timedelta():                          # D17: PG time vs MySQL TIME
    assert normalize_value(time(12, 30), "postgresql") == normalize_value(timedelta(hours=12, minutes=30), "mysql") == "12:30:00"
    assert normalize_value(timedelta(seconds=1.25), "mysql") == "00:00:01.25"
    assert normalize_value(timedelta(days=1), "postgresql") == "1 day, 0:00:00"
    assert normalize_value(timedelta(hours=-1), "mysql") == "-1 day, 23:00:00"


def test_year_padding():
    assert normalize_value(date(1, 1, 1), "postgresql") == "0001-01-01"


def test_uuid_json_list():                              # D18
    u = "6f1c2d3e-0000-4000-8000-000000000001"
    assert normalize_value(UUID(u), "postgresql") == u
    assert normalize_value({"b": 1, "a": "가"}, "postgresql") == '{"a": "가", "b": 1}'
    assert normalize_value([date(2024, 1, 1)], "postgresql") == '["2024-01-01"]'


def test_new_types_sortable_and_comparable():
    from sqlverdict import compare
    exp = {"columns": ["t", "u", "j"], "rows": [[time(12, 30), UUID(int=1), {"a": 1}], [time(9, 0), UUID(int=2), {"a": 2}]]}
    got = {"columns": ["t", "u", "j"], "rows": [[timedelta(hours=9), str(UUID(int=2)), '{"a": 2}'], [timedelta(hours=12, minutes=30), str(UUID(int=1)), '{"a": 1}']]}
    assert compare(exp, got, expected_dialect="postgresql", got_dialect="mysql").label == "correct"


def test_unknown_dialect_raises():
    with pytest.raises(ValueError, match="dialect"):
        normalize_value(1, "mysql ")


def test_oracle_empty_string_is_null():
    assert normalize_value("", "oracle") is None


@pytest.mark.parametrize("dialect", [d for d in DIALECTS if d != "oracle"])
def test_empty_string_kept_elsewhere(dialect):
    assert normalize_value("", dialect) == ""


@pytest.mark.parametrize("dialect", DIALECTS)
def test_null_zero_empty_stay_distinct(dialect):
    assert normalize_value(None, dialect) is None
    assert normalize_value(0, dialect) == 0


def test_mysql_and_postgresql_bool_agree():
    assert normalize_value(1, "mysql") == normalize_value(True, "postgresql") == 1


def test_normalize_rows():
    rows = [(Decimal("12.0"), date(2018, 1, 5), True, "A")]
    assert normalize_rows(rows, "postgresql") == [(12, "2018-01-05", 1, "A")]
