from html import escape

from sqlverdict.output.table import _acc, _info, _pct
from sqlverdict.score import STATUSES, VERDICTS

_CSP = "default-src 'none'; style-src 'unsafe-inline'"

_CSS = """
:root{--bg:#fff;--fg:#1f2328;--muted:#656d76;--line:#d0d7de;--head:#f6f8fa;
--bad:#cf222e;--bad-bg:#ffebe9;--warn:#9a6700;--warn-bg:#fff8c5;--err:#bc4c00;--err-bg:#fff1e5}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--muted:#8d96a0;--line:#30363d;
--head:#161b22;--bad:#ff7b72;--bad-bg:#3c1618;--warn:#d29922;--warn-bg:#2e2a1a;--err:#f0883e;--err-bg:#3a2414}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}
.meta{color:var(--muted)}
.warn{background:var(--warn-bg);color:var(--warn);border:1px solid var(--warn);border-radius:6px;padding:8px 12px;margin:12px 0}
.big{font-size:28px;font-weight:600}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{background:var(--head);white-space:nowrap}
tr.silent_wrong td:nth-child(2),tr.unscorable td:nth-child(2){color:var(--bad);background:var(--bad-bg);font-weight:600}
tr.error td:nth-child(2),tr.missing_prediction td:nth-child(2){color:var(--err);background:var(--err-bg)}
tr.correct_approx td:nth-child(2),tr.extra_columns td:nth-child(2){color:var(--warn);background:var(--warn-bg)}
"""


def esc(v):
    return escape("" if v is None else str(v), quote=True)


def _page(title, body):
    return (
        '<!doctype html>\n<html lang="ko"><head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{_CSP}">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)}</title><style>{_CSS}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )


def _table(headers, rows, row_class=None):
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = ""
    for i, r in enumerate(rows):
        cls = f' class="{esc(row_class[i])}"' if row_class else ""
        body += f"<tr{cls}>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>"
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _values(title, v):
    return f"<h3>{esc(title)}</h3>" + _table(v["columns"], v["rows"])


def render_html(report):
    run, s = report["run"], report["summary"]
    dialect = run["dialect"]
    if run.get("pred_dialect") and run["pred_dialect"] != dialect:
        dialect += f" → {run['pred_dialect']}"
    tol = "-" if run.get("tolerance") is None else f"{run['tolerance'] * 100:g}%"
    acc = _acc(s)

    parts = [
        "<h1>sqlverdict 보고서</h1>",
        f'<p class="meta">{esc(run["run_name"] or "-")} · {esc(dialect)} · snapshot {esc(run["snapshot"] or "-")}'
        f" · tolerance {esc(tol)} · v{esc(run['tool_version'])}</p>",
    ]
    parts += [f'<div class="warn">{esc(w)}</div>' for w in report["warnings"]]
    parts.append(f'<p><span class="big">{esc(acc)}</span> correct {s["correct"]} / 채점 {s["scored"]}'
                 f' / 전체 {s["total"]}</p>')
    parts.append(_table(list(VERDICTS) + list(STATUSES), [[s[k] for k in VERDICTS + STATUSES]]))
    if report["regressions"]:
        parts.append(f"<p>새로 틀림: {esc(', '.join(report['regressions']))}</p>")
    if report["improvements"]:
        parts.append(f"<p>새로 맞음: {esc(', '.join(report['improvements']))}</p>")

    for title, key in (("함정별", "by_trap"), ("난이도별", "by_level")):
        if report[key]:
            rows = [[k, g["total"], g["correct"], _pct(g["correct"], g["total"])] for k, g in report[key].items()]
            parts += [f"<h2>{title}</h2>", _table([title[:-1], "채점", "정답", "정답률"], rows)]

    shown = [r for r in report["items"] if r["label"] not in ("correct", "skipped_unverified")]
    if shown:
        rows = [[r["id"], r["label"], r["level"], r["trap"], r["question"], _info(r)] for r in shown]
        parts += ["<h2>고칠 문항</h2>",
                  _table(["id", "판정", "level", "trap", "질문", "안내"], rows, [r["label"] for r in shown])]

    with_values = [r for r in report["items"] if "got_head" in r or "expected" in r]
    if with_values:
        parts.append("<h2>결과 값 (옵션으로 포함됨)</h2>")
        for r in with_values:
            inner = ""
            if "expected" in r:
                inner += _values("정답", r["expected"])
            if "got_head" in r:
                inner += _values("예측 (앞부분)", r["got_head"])
            parts.append(f"<details><summary>{esc(r['id'])} · {esc(r['label'])}</summary>{inner}</details>")

    return _page(f"sqlverdict · {run['run_name'] or 'report'}", "".join(parts))
