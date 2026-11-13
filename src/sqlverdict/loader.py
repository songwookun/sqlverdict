import re

import yaml

from sqlverdict.model import Result
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
