import re
from dataclasses import fields
from datetime import date

import yaml

from sqlverdict.model import Golden, GoldenItem, PredItem, Predictions, Result
from sqlverdict.normalize import DIALECTS


class _Loader(yaml.SafeLoader):
    pass


# YAML 1.1의 yes/no/on/off → bool 변환 제거 (예: 국가 코드 NO가 False로 바뀌는 문제)
_Loader.yaml_implicit_resolvers = {
    ch: [r for r in rs if r[0] != "tag:yaml.org,2002:bool"]
    for ch, rs in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


class InputError(Exception):
    pass


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.load(f, Loader=_Loader)  # noqa: S506 — _Loader는 SafeLoader 하위 클래스
    except FileNotFoundError:
        raise InputError(f"파일이 없습니다: {path}") from None
    except yaml.YAMLError as e:
        raise InputError(f"YAML 형식 오류 ({path}): {e}") from None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise InputError(f"{path}: 최상위에 items 목록이 필요합니다")
    return data


def _dialect(value, path, required):
    if value is None and not required:
        return None
    if value not in DIALECTS:
        raise InputError(f"{path}: dialect는 {', '.join(DIALECTS)} 중 하나여야 합니다 (받은 값: {value!r})")
    return value


def _result(raw, unique_columns):
    if not isinstance(raw, dict) or not isinstance(raw.get("columns"), list) \
            or not isinstance(raw.get("rows"), list):
        return None, "columns와 rows 목록이 필요합니다"
    cols = [str(c) for c in raw["columns"]]
    if unique_columns and len({c.lower() for c in cols}) != len(cols):
        return None, "컬럼 이름이 중복됩니다"
    for i, row in enumerate(raw["rows"], 1):
        if not isinstance(row, list) or len(row) != len(cols):
            return None, f"{i}번째 행의 값 개수가 컬럼 수({len(cols)})와 다릅니다"
    return Result(cols, [tuple(r) for r in raw["rows"]]), None


_GOLDEN_KEYS = {f.name for f in fields(GoldenItem)} - {"problem"}
_BOOL_KEYS = ("verified", "ordered", "allow_extra_columns", "empty_ok")
_TEXT_KEYS = ("question", "level", "trap", "why", "gold_sql")


def _golden_item(raw, n):
    if not isinstance(raw, dict):
        return GoldenItem(id=f"#{n}", question=None, expected=None,
                          problem="문항이 '키: 값' 형식이 아닙니다")
    item_id = f"#{n}" if raw.get("id") is None else str(raw["id"])
    expected, p = _result(raw.get("expected"), unique_columns=True)
    problems = [p] if p else []

    unknown = sorted(set(raw) - _GOLDEN_KEYS, key=str)
    if unknown:
        problems.append(f"알 수 없는 필드: {', '.join(map(str, unknown))}")
    for k in _BOOL_KEYS:
        if k in raw and not isinstance(raw[k], bool):
            problems.append(f"{k}는 true 또는 false여야 합니다")
    tol = raw.get("tolerance")
    if tol is not None and (isinstance(tol, bool) or not isinstance(tol, (int, float)) or tol < 0):
        problems.append("tolerance는 0 이상의 숫자여야 합니다")
    cc = raw.get("compare_columns")
    if cc is not None:
        if not isinstance(cc, list) or not cc:
            problems.append("compare_columns는 비어 있지 않은 목록이어야 합니다")
        elif expected and not {str(c) for c in cc} <= set(expected.columns):
            problems.append("compare_columns에 정답 표에 없는 컬럼이 있습니다")

    kw = {k: raw[k] for k in _GOLDEN_KEYS - {"id", "expected"} if k in raw}
    kw.setdefault("question", None)
    for k in _TEXT_KEYS:
        if kw.get(k) is not None:
            kw[k] = str(kw[k])
    if isinstance(cc, list):
        kw["compare_columns"] = [str(c) for c in cc]
    return GoldenItem(id=item_id, expected=expected,
                      problem="; ".join(problems) or None, **kw)


_PRED_KEYS = {"id", "result", "error", "pred_sql"}


def _pred_item(raw, n):
    if not isinstance(raw, dict):
        return PredItem(id=f"#{n}", problem="문항이 '키: 값' 형식이 아닙니다")
    item_id = f"#{n}" if raw.get("id") is None else str(raw["id"])
    problems = []
    unknown = sorted(set(raw) - _PRED_KEYS, key=str)
    if unknown:
        problems.append(f"알 수 없는 필드: {', '.join(map(str, unknown))}")
    has_result, has_error = raw.get("result") is not None, raw.get("error") is not None
    if has_result == has_error:
        problems.append("result와 error 중 정확히 하나가 필요합니다")
    result = None
    if has_result:
        result, p = _result(raw["result"], unique_columns=False)
        if p:
            problems.append(p)
    return PredItem(id=item_id, result=result,
                    error=str(raw["error"]) if has_error else None,
                    pred_sql=None if raw.get("pred_sql") is None else str(raw["pred_sql"]),
                    problem="; ".join(problems) or None)


_GOLDEN_TOP = {"dialect", "snapshot", "items"}
_PRED_TOP = {"run_name", "dialect", "items"}


def _check_top(data, allowed, path):
    unknown = sorted(set(data) - allowed, key=str)
    if unknown:
        raise InputError(f"{path}: 알 수 없는 최상위 필드: {', '.join(map(str, unknown))}")


def _snapshot(v):
    if v is None:
        return None
    return v.isoformat() if isinstance(v, date) else str(v)


def load_golden(path):
    data = _read(path)
    _check_top(data, _GOLDEN_TOP, path)
    return Golden(dialect=_dialect(data.get("dialect"), path, required=True),
                  snapshot=_snapshot(data.get("snapshot")),
                  items=[_golden_item(r, n) for n, r in enumerate(data["items"], 1)])


def load_predictions(path):
    data = _read(path)
    _check_top(data, _PRED_TOP, path)
    run_name = data.get("run_name")
    return Predictions(run_name=None if run_name is None else str(run_name),
                       dialect=_dialect(data.get("dialect"), path, required=False),
                       items=[_pred_item(r, n) for n, r in enumerate(data["items"], 1)])
