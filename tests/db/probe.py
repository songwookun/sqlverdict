"""DB마다 같은 값을 SELECT해서 드라이버가 돌려주는 파이썬 타입과 normalize 결과를 출력한다.
사용: python tests/db/probe.py [mysql] [postgresql] [oracle]   (기본: mysql postgresql)
"""
import sys

from sqlverdict.normalize import normalize_value

CASES = {
    "mysql": [
        ("int", "1"),
        ("decimal", "CAST(152340.3333 AS DECIMAL(12,4))"),
        ("decimal_int", "CAST(100 AS DECIMAL(10,2))"),
        ("decimal_big", "CAST(12345678901234.5678 AS DECIMAL(20,4))"),
        ("float", "CAST(0.1 AS FLOAT)"),
        ("double", "CAST(0.1 AS DOUBLE)"),
        ("bool", "TRUE"),
        ("date", "DATE '2024-01-01'"),
        ("datetime", "CAST('2024-01-01 12:00:00.5' AS DATETIME(6))"),
        ("time", "TIME '12:30:00'"),
        ("uuid", "'6f1c2d3e-0000-4000-8000-000000000001'"),
        ("json", "JSON_OBJECT('a', 1)"),
        ("empty", "''"),
    ],
    "postgresql": [
        ("int", "1"),
        ("decimal", "152340.3333::numeric(12,4)"),
        ("decimal_int", "100::numeric(10,2)"),
        ("decimal_big", "12345678901234.5678::numeric(20,4)"),
        ("decimal_nan", "'NaN'::numeric"),
        ("float", "0.1::real"),
        ("double", "0.1::float8"),
        ("bool", "TRUE"),
        ("date", "DATE '2024-01-01'"),
        ("datetime", "TIMESTAMP '2024-01-01 12:00:00.5'"),
        ("timestamptz", "TIMESTAMPTZ '2024-01-01 12:00:00+09'"),
        ("time", "TIME '12:30:00'"),
        ("interval", "INTERVAL '1 day'"),
        ("uuid", "'6f1c2d3e-0000-4000-8000-000000000001'::uuid"),
        ("json", "'{\"a\": 1}'::jsonb"),
        ("empty", "''"),
        ("char", "CAST('A' AS CHAR(3))"),
    ],
    "oracle": [
        ("int", "1"),
        ("decimal", "CAST(152340.3333 AS NUMBER(12,4))"),
        ("decimal_int", "CAST(100 AS NUMBER(10,2))"),
        ("decimal_big", "CAST(12345678901234.5678 AS NUMBER(20,4))"),
        ("float", "TO_BINARY_FLOAT(0.1)"),
        ("double", "TO_BINARY_DOUBLE(0.1)"),
        ("bool", "TRUE"),
        ("date", "DATE '2024-01-01'"),
        ("datetime", "TIMESTAMP '2024-01-01 12:00:00.5'"),
        ("timestamptz", "TIMESTAMP '2024-01-01 12:00:00 +09:00'"),
        ("interval", "INTERVAL '1' DAY"),
        ("empty", "''"),
        ("char", "CAST('A' AS CHAR(3))"),
    ],
}


def connect(dialect):
    if dialect == "mysql":
        import pymysql
        return pymysql.connect(host="127.0.0.1", port=13306, user="root", password="sv", database="sv")
    if dialect == "postgresql":
        import psycopg
        return psycopg.connect("host=127.0.0.1 port=15432 user=postgres password=sv dbname=sv")
    import oracledb
    return oracledb.connect(user="sv", password="sv", dsn="127.0.0.1:11521/FREEPDB1")


def probe(dialect):
    conn = connect(dialect)
    cur = conn.cursor()
    tail = " FROM dual" if dialect == "oracle" else ""
    for name, expr in CASES[dialect]:
        try:
            cur.execute(f"SELECT {expr}{tail}")
            v = cur.fetchone()[0]
            print(f"{dialect:10} {name:12} {type(v).__name__:10} {v!r:45} -> {normalize_value(v, dialect)!r}")
        except Exception as e:
            print(f"{dialect:10} {name:12} 실패: {type(e).__name__}: {e}")
            conn.rollback()
    conn.close()


if __name__ == "__main__":
    for d in sys.argv[1:] or ["mysql", "postgresql"]:
        probe(d)
