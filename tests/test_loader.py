import pytest
import yaml

from sqlverdict.loader import InputError, _dialect, _read, _result


def write(tmp_path, text):
    p = tmp_path / "f.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_norway_stays_string(tmp_path):
    data = _read(write(tmp_path, "items:\n  - rows: [[NO, yes, on, off, Y]]\n"))
    assert data["items"][0]["rows"] == [["NO", "yes", "on", "off", "Y"]]


def test_true_false_are_bool(tmp_path):
    data = _read(write(tmp_path, "items:\n  - a: true\n    b: False\n"))
    assert data["items"][0] == {"a": True, "b": False}


def test_safe_loader_original_untouched():
    assert yaml.safe_load("x: yes") == {"x": True}


def test_python_tag_rejected(tmp_path):
    p = write(tmp_path, "items: !!python/object/apply:os.system ['echo hi']\n")
    with pytest.raises(InputError, match="YAML"):
        _read(p)


def test_missing_file(tmp_path):
    with pytest.raises(InputError, match="파일이 없습니다"):
        _read(tmp_path / "nope.yaml")


def test_broken_yaml(tmp_path):
    with pytest.raises(InputError, match="YAML 형식 오류"):
        _read(write(tmp_path, "items: [\n"))


def test_items_required(tmp_path):
    with pytest.raises(InputError, match="items"):
        _read(write(tmp_path, "dialect: mysql\n"))


def test_dialect_typo():
    with pytest.raises(InputError, match="dialect"):
        _dialect("postgres", "g.yaml", required=True)


def test_dialect_optional():
    assert _dialect(None, "p.yaml", required=False) is None
    with pytest.raises(InputError):
        _dialect(None, "g.yaml", required=True)


def test_result_ok():
    r, problem = _result({"columns": ["a", "b"], "rows": [[1, 2]]}, unique_columns=True)
    assert problem is None and r.rows == [(1, 2)]


def test_result_shape_missing():
    assert _result({"columns": ["a"]}, True) == (None, "columns와 rows 목록이 필요합니다")
    assert _result(None, True)[0] is None


def test_result_row_length():
    _, problem = _result({"columns": ["a", "b"], "rows": [[1, 2], [3]]}, True)
    assert problem == "2번째 행의 값 개수가 컬럼 수(2)와 다릅니다"


def test_duplicate_columns_only_blocked_for_expected():
    raw = {"columns": ["id", "ID"], "rows": [[1, 2]]}
    assert _result(raw, unique_columns=True)[1] == "컬럼 이름이 중복됩니다"
    assert _result(raw, unique_columns=False)[1] is None
