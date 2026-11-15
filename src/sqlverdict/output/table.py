import unicodedata

from sqlverdict.score import STATUSES, VERDICTS

QUESTION_W, INFO_W = 30, 70


def _width(s):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def _cut(s, limit):
    s = " ".join(str(s).split())
    out, w = "", 0
    for ch in s:
        cw = _width(ch)
        if w + cw > limit - 1:
            return out + "…"
        out, w = out + ch, w + cw
    return out


def _pad(s, width, right=False):
    fill = " " * (width - _width(s))
    return fill + s if right else s + fill


def _table(headers, rows, right=()):
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(_width(x) for x in col) for col in zip(headers, *rows)]

    def line(cells):
        return "  ".join(_pad(c, w, i in right) for i, (c, w) in enumerate(zip(cells, widths))).rstrip()

    return "\n".join([line(headers), line(["-" * w for w in widths])] + [line(r) for r in rows])


def _pct(a, b):
    return f"{a / b:.1%}" if b else "-"


def _groups(title, groups):
    rows = [[k, g["total"], g["correct"], _pct(g["correct"], g["total"])] for k, g in groups.items()]
    return _table([title, "채점", "정답", "정답률"], rows, right={1, 2, 3})


def _info(r):
    if r.get("reason"):
        return r["reason"]
    if r.get("error"):
        return "실행 실패: " + r["error"]
    return " / ".join(r["hints"])


def render_table(report):
    run, s = report["run"], report["summary"]
    dialect = run["dialect"]
    if run.get("pred_dialect") and run["pred_dialect"] != dialect:
        dialect += f" → {run['pred_dialect']}"
    head = (f"sqlverdict {run['tool_version']} · {run['run_name'] or '-'} · {dialect}"
            f" · snapshot {run['snapshot'] or '-'}")
    blocks = [head]
    if report["warnings"]:
        blocks.append("\n".join(f"! {w}" for w in report["warnings"]))

    acc = "-" if s["accuracy"] is None else f"{s['accuracy']:.1%}"
    lines = [f"정확도 {acc}  (correct {s['correct']} / 채점 {s['scored']} / 전체 {s['total']})",
             "판정  " + " · ".join(f"{k} {s[k]}" for k in VERDICTS),
             "제외  " + " · ".join(f"{k} {s[k]}" for k in STATUSES)]
    if report["regressions"]:
        lines.append("새로 틀림  " + ", ".join(report["regressions"]))
    if report["improvements"]:
        lines.append("새로 맞음  " + ", ".join(report["improvements"]))
    blocks.append("\n".join(lines))

    if report["by_trap"]:
        blocks.append(_groups("함정", report["by_trap"]))
    if report["by_level"]:
        blocks.append(_groups("난이도", report["by_level"]))

    shown = [r for r in report["items"] if r["label"] not in ("correct", "skipped_unverified")]
    if shown:
        rows = [[r["id"], r["label"], r["level"] or "-", r["trap"] or "-",
                 _cut(r["question"] or "-", QUESTION_W), _cut(_info(r), INFO_W)] for r in shown]
        blocks.append(_table(["id", "판정", "level", "trap", "질문", "안내"], rows))
    return "\n\n".join(blocks)
