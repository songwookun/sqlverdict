import json
import math
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

DIALECTS = ("sqlite", "mysql", "postgresql", "oracle")


def _number(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, Decimal):
        if v.is_nan():
            return "NaN"
        if v.is_finite() and v == v.to_integral_value():
            return int(v)
        return float(v)
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if v.is_integer():
            return int(v)
    return v


def _other(v):
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)
    return v


def _clock(h, m, s, us):
    frac = f".{us:06d}".rstrip("0") if us else ""
    return f"{h:02d}:{m:02d}:{s:02d}{frac}"


def _day(v):
    return f"{v.year:04d}-{v.month:02d}-{v.day:02d}"


def _temporal(v):
    if isinstance(v, datetime):
        if v.utcoffset() is not None:
            v = v.astimezone(timezone.utc)
            return f"{_day(v)} {_clock(v.hour, v.minute, v.second, v.microsecond)}+00:00"
        if v.time() == time(0):
            return _day(v)
        return f"{_day(v)} {_clock(v.hour, v.minute, v.second, v.microsecond)}"
    if isinstance(v, date):
        return _day(v)
    if isinstance(v, time):
        return _clock(v.hour, v.minute, v.second, v.microsecond)
    if isinstance(v, timedelta):
        if timedelta(0) <= v < timedelta(days=1):
            h, rest = divmod(v.seconds, 3600)
            return _clock(h, *divmod(rest, 60), v.microseconds)
        return str(v)
    return v


def normalize_value(v, dialect):
    if dialect not in DIALECTS:
        raise ValueError(f"지원하지 않는 dialect: {dialect!r} (가능: {', '.join(DIALECTS)})")
    if dialect == "oracle" and v == "":
        return None
    return _number(_other(_temporal(v)))


def normalize_rows(rows, dialect):
    return [tuple(normalize_value(v, dialect) for v in row) for row in rows]
