import argparse
import json
import os
import sys
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path

from sqlverdict._version import __version__
from sqlverdict.check import check
from sqlverdict.compare import DEFAULT_TOLERANCE
from sqlverdict.loader import InputError, load_golden, load_predictions
from sqlverdict.output.html_out import render_html
from sqlverdict.output.json_out import to_json
from sqlverdict.output.table import render_table
from sqlverdict.score import STATUSES, VERDICTS, score

FAIL_CHOICES = tuple(x for x in VERDICTS + STATUSES if x != "correct")
TEMPLATES = ("golden.yaml", "predictions.yaml", "AGENTS.md")
RENDER = {"table": render_table, "json": to_json, "html": render_html}


def _non_negative(kind):
    def conv(s):
        v = kind(s)
        if v < 0:
            raise argparse.ArgumentTypeError(f"0 이상이어야 합니다: {s}")
        return v
    return conv


def _parser():
    p = argparse.ArgumentParser(prog="sqlverdict", description="Text-to-SQL 결과 채점기")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="예시 golden.yaml·predictions.yaml·AGENTS.md 생성")
    i.add_argument("dir", nargs="?", default="evals", help="만들 폴더 (기본 evals)")
    i.add_argument("--force", action="store_true", help="이미 있는 파일 덮어쓰기")

    c = sub.add_parser("check", help="골든셋 검사 (+ 예측 id 짝 확인)")
    c.add_argument("golden")
    c.add_argument("predictions", nargs="?")
    c.add_argument("--format", choices=("table", "json"), default="table")

    s = sub.add_parser("score", help="채점")
    s.add_argument("golden")
    s.add_argument("predictions")
    s.add_argument("--format", choices=("table", "json", "html"), default="table")
    s.add_argument("-o", "--output", help="저장할 파일 (없으면 화면 출력)")
    s.add_argument("--tolerance", type=_non_negative(float), default=DEFAULT_TOLERANCE)
    s.add_argument("--baseline", help="이전 실행의 JSON 결과")
    s.add_argument("--fail-on", action="append", choices=FAIL_CHOICES, default=[])
    s.add_argument("--head", type=_non_negative(int), default=0)
    s.add_argument("--include-expected", action="store_true")
    s.add_argument("--include-unverified", action="store_true")
    return p


def _write(text, path=None):
    if not text.endswith("\n"):
        text += "\n"
    if path:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"저장: {path}", file=sys.stderr)
        return
    if not sys.stdout.isatty() and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(text)
    sys.stdout.flush()


def _cmd_check(args):
    golden = load_golden(args.golden)
    preds = load_predictions(args.predictions) if args.predictions else None
    issues = sorted(check(golden, preds), key=lambda i: i.severity != "error")
    errors = sum(i.severity == "error" for i in issues)
    if args.format == "json":
        _write(to_json({
            "schema_version": "1",
            "run": {"golden": args.golden, "predictions": args.predictions,
                    "tool_version": __version__},
            "summary": {"error": errors, "warn": len(issues) - errors},
            "issues": [asdict(i) for i in issues],
        }))
    else:
        for i in issues:
            print(f"[{i.severity}] {i.id or '(전체)'}: {i.message}")
        print(f"error {errors}개 · warn {len(issues) - errors}개" if issues else "문제 없음")
    return 1 if errors else 0


def _load_baseline(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise InputError(f"파일이 없습니다: {path}") from None
    except json.JSONDecodeError as e:
        raise InputError(f"JSON 형식 오류 ({path}): {e}") from None
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not all(isinstance(r, dict) and "id" in r and "label" in r
                                              for r in items):
        raise InputError(f"{path}: sqlverdict score --format json 결과가 아닙니다")
    return data


def _cmd_score(args):
    golden = load_golden(args.golden)
    preds = load_predictions(args.predictions)
    baseline = _load_baseline(args.baseline) if args.baseline else None
    report = score(golden, preds, tolerance=args.tolerance,
                   include_unverified=args.include_unverified, head=args.head,
                   include_expected=args.include_expected, baseline=baseline,
                   golden_path=args.golden, preds_path=args.predictions)
    _write(RENDER[args.format](report), args.output)
    hit = {k: report["summary"][k] for k in args.fail_on if report["summary"][k]}
    if hit:
        print("--fail-on 걸림: " + ", ".join(f"{k} {n}개" for k, n in hit.items()), file=sys.stderr)
        return 1
    return 0


def _cmd_init(args):
    dest = Path(args.dir)
    exists = [n for n in TEMPLATES if (dest / n).exists()]
    if exists and not args.force:
        print(f"이미 있음: {', '.join(exists)} (덮어쓰려면 --force)", file=sys.stderr)
        return 2
    dest.mkdir(parents=True, exist_ok=True)
    src = files("sqlverdict") / "templates"
    for n in TEMPLATES:
        (dest / n).write_text((src / n).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        print(f"생성: {dest / n}")
    print(f"다음: sqlverdict check {dest / 'golden.yaml'} → 예시 데이터를 실제 DB 정답으로 교체")
    return 0


COMMANDS = {"init": _cmd_init, "check": _cmd_check, "score": _cmd_score}


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        return COMMANDS[args.cmd](args)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
    except (InputError, OSError) as e:
        print(f"sqlverdict: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
