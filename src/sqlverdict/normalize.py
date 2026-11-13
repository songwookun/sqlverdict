from datetime import date, datetime
from decimal import Decimal

DIALECTS = ("sqlite", "mysql", "postgresql", "oracle")


def _number(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, Decimal):
        if v.is_finite() and v == v.to_integral_value():
            return int(v)
        return float(v)
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _date(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    return v


def normalize_value(v, dialect):
    if dialect not in DIALECTS:
        raise ValueError(f"지원하지 않는 dialect: {dialect!r} (가능: {', '.join(DIALECTS)})")
    if dialect == "oracle" and v == "":
        return None
    return _number(_date(v))


def normalize_rows(rows, dialect):
    return [tuple(normalize_value(v, dialect) for v in row) for row in rows]
