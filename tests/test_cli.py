import json

import pytest

from sqlverdict.cli import main


@pytest.fixture
def ev(tmp_path):
    assert main(["init", str(tmp_path / "evals")]) == 0
    return tmp_path / "evals"


def paths(ev):
    return [str(ev / "golden.yaml"), str(ev / "predictions.yaml")]


# init
def test_init_creates_three_files(ev):
    assert sorted(p.name for p in ev.iterdir()) == ["AGENTS.md", "golden.yaml", "predictions.yaml"]


def test_init_refuses_existing_without_writing(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("mine", encoding="utf-8")
    assert main(["init", str(tmp_path)]) == 2
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "mine"
    assert not (tmp_path / "golden.yaml").exists()
    assert "--force" in capsys.readouterr().err


def test_init_force_overwrites(ev):
    (ev / "golden.yaml").write_text("x", encoding="utf-8")
    assert main(["init", str(ev), "--force"]) == 0
    assert "가상 데이터" in (ev / "golden.yaml").read_text(encoding="utf-8")


# check
def test_check_template_has_no_errors(ev, capsys):
    assert main(["check", *paths(ev)]) == 0
    assert "error 0개" in capsys.readouterr().out


def test_check_error_exits_1(ev, capsys):
    g = ev / "golden.yaml"
    g.write_text(g.read_text(encoding="utf-8").replace("  - id: Q002", "  - id: Q001"), encoding="utf-8")
    assert main(["check", str(g)]) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("[error] Q001")


# score
def test_score_template_demo(ev, capsys):
    assert main(["score", *paths(ev), "--format", "json"]) == 0
    s = json.loads(capsys.readouterr().out)["summary"]
    assert (s["correct"], s["correct_approx"], s["silent_wrong"], s["error"], s["skipped_unverified"]) == (2, 1, 1, 1, 1)


@pytest.mark.parametrize("fail_on,code", [(["silent_wrong"], 1), (["extra_columns"], 0),
                                          (["extra_columns", "error"], 1)])
def test_fail_on(ev, capsys, fail_on, code):
    args = [a for f in fail_on for a in ("--fail-on", f)]
    assert main(["score", *paths(ev), *args]) == code
    assert ("--fail-on 걸림" in capsys.readouterr().err) == bool(code)


@pytest.mark.parametrize("fmt,start", [("json", "{"), ("html", "<!doctype html>"), ("table", "sqlverdict ")])
def test_output_file(ev, capsys, fmt, start):
    out = ev / f"r.{fmt}"
    assert main(["score", *paths(ev), "--format", fmt, "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith(start)
    assert capsys.readouterr().out == ""


def test_baseline_round_trip(ev, capsys):
    base = ev / "base.json"
    main(["score", *paths(ev), "--format", "json", "-o", str(base)])
    p = ev / "predictions.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("rows: [[1240]]", "rows: [[1241]]"), encoding="utf-8")
    main(["score", *paths(ev), "--format", "json", "--baseline", str(base)])
    assert json.loads(capsys.readouterr().out)["regressions"] == ["Q001"]


# 입력 오류 → 2
@pytest.mark.parametrize("extra", [["--baseline", "nope.json"], ["-o", "/nonexist/dir/r.txt"],
                                   ["--tolerance", "-1"], ["--fail-on", "correct"]])
def test_input_errors_exit_2(ev, extra):
    try:
        code = main(["score", *paths(ev), *extra])
    except SystemExit as e:
        code = e.code
    assert code == 2


def test_bad_baseline_json_shape(ev, capsys):
    bad = ev / "bad.json"
    bad.write_text('{"name": "x"}', encoding="utf-8")
    assert main(["score", *paths(ev), "--baseline", str(bad)]) == 2
    assert "결과가 아닙니다" in capsys.readouterr().err


def test_missing_golden_exit_2(tmp_path, capsys):
    assert main(["check", str(tmp_path / "nope.yaml")]) == 2
    assert capsys.readouterr().err.startswith("sqlverdict: ")
