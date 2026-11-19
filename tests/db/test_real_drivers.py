import pytest
from probe import CASES, connect

from sqlverdict.normalize import normalize_value

pytestmark = pytest.mark.db

# 세 DB가 같은 표준형이어야 하는 값 (R1~R5 해결 확인)
SAME = {
    "int": 1, "decimal": 152340.3333, "decimal_int": 100, "decimal_big": 12345678901234.568,
    "double": 0.1, "bool": 1, "date": "2024-01-01", "datetime": "2024-01-01 12:00:00.5",
    "time": "12:30:00", "interval": "1 day, 0:00:00", "decimal_nan": "NaN",
    "uuid": "6f1c2d3e-0000-4000-8000-000000000001", "json": '{"a": 1}',
}
# DB마다 다른 게 정상이거나 알려진 한계인 값 (바뀌면 README 갱신)
PER_DB = {
    ("mysql", "float"): 0.1,
    ("postgresql", "float"): 0.1,
    ("oracle", "float"): 0.10000000149011612,           # BINARY_FLOAT 단정밀도 (D1 한계)
    ("postgresql", "timestamptz"): "2024-01-01 03:00:00+00:00",
    ("oracle", "timestamptz"): "2024-01-01 12:00:00",   # thin이 tz를 버림 → SYS_EXTRACT_UTC 안내
    ("mysql", "empty"): "", ("postgresql", "empty"): "",
    ("oracle", "empty"): None,                          # Oracle은 ''를 NULL로 저장
    ("postgresql", "char"): "A  ", ("oracle", "char"): "A  ",   # CHAR 공백 (R7 한계)
}
PARAMS = [(d, name, expr) for d, cases in CASES.items() for name, expr in cases]
_conns = {}


def _cursor(dialect):
    if dialect not in _conns:
        try:
            _conns[dialect] = connect(dialect)
        except Exception as e:
            _conns[dialect] = e
    c = _conns[dialect]
    if isinstance(c, Exception):
        pytest.skip(f"{dialect} 접속 불가 ({type(c).__name__}): tests/db/docker-compose.yml로 먼저 띄울 것")
    return c.cursor()


@pytest.fixture(scope="module", autouse=True)
def _close_all():
    yield
    for c in _conns.values():
        if not isinstance(c, Exception):
            c.close()


@pytest.mark.parametrize("dialect,name,expr", PARAMS, ids=[f"{d}-{n}" for d, n, _ in PARAMS])
def test_driver_value(dialect, name, expr):
    assert (dialect, name) in PER_DB or name in SAME, "기대값 표에 케이스 추가 필요"
    cur = _cursor(dialect)
    cur.execute(f"SELECT {expr}" + (" FROM dual" if dialect == "oracle" else ""))
    got = normalize_value(cur.fetchone()[0], dialect)
    assert got == PER_DB.get((dialect, name), SAME.get(name))
