import math
from datetime import date, datetime
from decimal import Decimal

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
    assert math.isnan(_number(Decimal("NaN")))


def test_datetime_keeps_time():
    assert normalize_value(datetime(2018, 1, 5, 13, 4, 9), "mysql") == "2018-01-05 13:04:09"


def test_date_becomes_string():
    assert normalize_value(date(2018, 1, 5), "postgresql") == "2018-01-05"


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
