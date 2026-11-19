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


def test_check_json(ev, capsys):
    assert main(["check", *paths(ev), "--format", "json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["schema_version"] == "1"
    assert d["summary"] == {"error": 0, "warn": 2}
    assert {i["id"] for i in d["issues"]} == {None, "Q006"}
    assert set(d["issues"][0]) == {"severity", "id", "message"}


def test_check_json_error_first_and_exit_1(ev, capsys):
    g = ev / "golden.yaml"
    g.write_text(g.read_text(encoding="utf-8").replace("  - id: Q002", "  - id: Q001"), encoding="utf-8")
    assert main(["check", str(g), "--format", "json"]) == 1
    d = json.loads(capsys.readouterr().out)
    assert d["summary"]["error"] == 1
    assert d["issues"][0]["severity"] == "error" and d["issues"][0]["id"] == "Q001"
    assert d["run"]["predictions"] is None


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


def test_check_escapes_control_chars(ev, capsys):
    g = ev / "golden.yaml"
    g.write_text(g.read_text(encoding="utf-8").replace("  - id: Q006", '  - id: "Q006\\e[2J"'), encoding="utf-8")
    main(["check", str(g)])
    out = capsys.readouterr().out
    assert "\x1b" not in out and "Q006\\x1b[2J" in out


def test_error_message_escapes_control_chars(tmp_path, capsys):
    g = tmp_path / "g.yaml"
    g.write_text('dialect: sqlite\n"\\e]0;HACK\\a": 1\nitems: []\n', encoding="utf-8")
    assert main(["check", str(g)]) == 2
    err = capsys.readouterr().err
    assert "\x1b" not in err and "\\x1b]0;HACK" in err


@pytest.mark.parametrize("fmt", ["table", "json", "html"])
def test_surrogate_does_not_crash(ev, capsys, fmt):
    g = ev / "golden.yaml"
    g.write_text(g.read_text(encoding="utf-8").replace("  - id: Q006", '  - id: "Q\\ud800"'), encoding="utf-8")
    assert main(["score", *paths(ev), "--include-unverified", "--format", fmt]) == 0
    assert "\\ud800" in capsys.readouterr().out


def test_non_utf8_input_exit_2(tmp_path, capsys):
    g = tmp_path / "g.yaml"
    g.write_bytes("dialect: sqlite\nitems:\n  - id: 한\n".encode("cp949"))
    assert main(["check", str(g)]) == 2
    assert "UTF-8" in capsys.readouterr().err


def test_non_utf8_baseline_exit_2(ev, capsys):
    b = ev / "b.json"
    b.write_bytes(b'{"items": [\xff')
    assert main(["score", *paths(ev), "--baseline", str(b)]) == 2
