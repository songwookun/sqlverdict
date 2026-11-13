from sqlverdict.model import Result, Verdict

# 계산 오차만 흡수 (numpy 기본 1e-5는 큰 금액에서 너무 너그러움 → code_design.md 결정 D1)
STRICT_RTOL, STRICT_ATOL = 1e-9, 1e-9


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def cell_match(exp, got, tolerance):
    if exp is None or got is None:
        return "strict" if exp is None and got is None else None
    if _is_num(exp) and _is_num(got):
        diff = abs(exp - got)
        noise = STRICT_ATOL + STRICT_RTOL * abs(exp)
        if diff <= noise:
            return "strict"
        if diff <= tolerance + noise:
            return "approx"
        return None
    return "strict" if exp == got else None


def match_columns(exp_cols, got_cols, want):
    lower = [c.lower() for c in got_cols]
    by_name = {c: lower.index(c.lower()) for c in want if c.lower() in lower}
    used = set(by_name.values())
    mapping = dict(by_name)
    for c in want:
        if c in mapping:
            continue
        i = exp_cols.index(c)
        mapping[c] = i if i < len(got_cols) and i not in used else None
    matched_by = "name" if len(by_name) == len(want) else "position"
    return mapping, matched_by


def sort_key(row):
    return tuple(
        (0, 0) if v is None else (1, v) if _is_num(v) else (2, str(v))
        for v in row
    )


def _project(rows, idx):
    return [tuple(r[i] for i in idx) for r in rows]


def _as_result(r):
    if isinstance(r, Result):
        return r
    return Result(list(r["columns"]), [tuple(row) for row in r["rows"]])


def compare(expected, got, *, dialect=None, expected_dialect=None, got_dialect=None,
            ordered=False, compare_columns=None, allow_extra_columns=False, tolerance=0.01):
    exp_d = expected_dialect or dialect
    got_d = got_dialect or dialect or exp_d
    if exp_d is None:
        raise ValueError("dialect 또는 expected_dialect가 필요합니다")
    exp, got = _as_result(expected), _as_result(got)
    want = list(compare_columns or exp.columns)
    mapping, matched_by = match_columns(exp.columns, got.columns, want)
    detail = {
        "expected_rows": len(exp.rows), "got_rows": len(got.rows), "matched_by": matched_by,
        "column_map": {c: got.columns[i] for c, i in mapping.items()
                       if i is not None and got.columns[i] != c},
    }
    missing = [c for c, i in mapping.items() if i is None]
    if missing:
        detail["missing_columns"] = missing
        return Verdict("silent_wrong", detail)
    raise NotImplementedError("값 비교는 블록 2/2에서")
