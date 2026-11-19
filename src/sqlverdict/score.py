from datetime import date

from sqlverdict._version import __version__
from sqlverdict.check import STALE_DAYS
from sqlverdict.compare import DEFAULT_TOLERANCE, compare
from sqlverdict.normalize import normalize_rows

VERDICTS = ("correct", "correct_approx", "extra_columns", "silent_wrong", "error")
STATUSES = ("skipped_unverified", "unscorable", "missing_prediction")
ERROR_MAX = 300
MASS_FAIL_MIN, MASS_FAIL_RATIO = 3, 0.2


def _score_item(it, pred, *, golden_dialect, pred_dialect, tolerance,
                include_unverified=False, head=0, include_expected=False):
    rec = {"id": it.id, "question": it.question, "level": it.level, "trap": it.trap,
           "label": None, "diff": {}, "hints": []}
    if it.problem:
        rec.update(label="unscorable", reason=it.problem)
    elif not it.verified and not include_unverified:
        rec["label"] = "skipped_unverified"
    elif pred is None:
        rec["label"] = "missing_prediction"
    elif pred.problem:
        rec.update(label="unscorable", reason=pred.problem)
    elif pred.error is not None:
        rec.update(label="error", error=pred.error[:ERROR_MAX])
    else:
        v = compare(it.expected, pred.result,
                    expected_dialect=golden_dialect, got_dialect=pred_dialect or golden_dialect,
                    ordered=it.ordered, compare_columns=it.compare_columns,
                    allow_extra_columns=it.allow_extra_columns,
                    tolerance=tolerance if it.tolerance is None else it.tolerance,
                    pred_sql=pred.pred_sql)
        rec.update(label=v.label, diff=v.detail, hints=v.hints)
        if head:
            rows = normalize_rows(pred.result.rows[:head], pred_dialect or golden_dialect)
            rec["got_head"] = {"columns": pred.result.columns, "rows": [list(r) for r in rows]}
    if include_expected and it.expected:
        rows = normalize_rows(it.expected.rows, golden_dialect)
        rec["expected"] = {"columns": it.expected.columns, "rows": [list(r) for r in rows]}
    return rec


def _summary(records):
    summary = {"total": len(records)}
    for name in STATUSES + VERDICTS:
        summary[name] = sum(r["label"] == name for r in records)
    scored = sum(summary[v] for v in VERDICTS)
    summary["scored"] = scored
    summary["accuracy"] = round(summary["correct"] / scored, 3) if scored else None
    return summary


def _group(records, key):
    out = {}
    for r in records:
        if r["label"] not in VERDICTS:
            continue
        g = out.setdefault(r[key] or "unknown", {"total": 0, "correct": 0})
        g["total"] += 1
        g["correct"] += r["label"] == "correct"
    return dict(sorted(out.items()))


def _baseline_diff(records, baseline):
    before = {r["id"]: r["label"] for r in baseline.get("items", [])}
    regressions, improvements = [], []
    for r in records:
        prev, now = before.get(r["id"]), r["label"]
        if prev is None or now not in VERDICTS or prev not in VERDICTS:
            continue
        if prev == "correct" and now != "correct":
            regressions.append(r["id"])
        elif prev != "correct" and now == "correct":
            improvements.append(r["id"])
    return regressions, improvements


def _warnings(golden, preds, records, regressions, today):
    out = []
    if golden.snapshot:
        try:
            age = (today - date.fromisoformat(golden.snapshot)).days
        except ValueError:
            age = None
        if age is not None and age > STALE_DAYS:
            out.append(f"snapshot이 {age}일 지남: 정답 다시 뽑기 권장")
    scored = sum(r["label"] in VERDICTS for r in records)
    if len(regressions) >= max(MASS_FAIL_MIN, MASS_FAIL_RATIO * scored):
        out.append(f"이전 실행 대비 {len(regressions)}문항이 한꺼번에 틀림: "
                   "SQL 문제가 아니라 DB 데이터가 바뀌어 정답이 낡았을 수 있음")
    gold_ids = {it.id for it in golden.items}
    unknown = [p.id for p in preds.items if p.id not in gold_ids]
    if unknown:
        out.append(f"골든셋에 없는 예측 id {len(unknown)}개는 채점하지 않음 (check로 확인)")
    return out


def score(golden, preds, *, tolerance=DEFAULT_TOLERANCE, include_unverified=False, head=0,
          include_expected=False, baseline=None, today=None,
          golden_path=None, preds_path=None):
    today = today or date.today()
    by_id = {}
    for p in preds.items:
        by_id.setdefault(p.id, p)
    records = [_score_item(it, by_id.get(it.id), golden_dialect=golden.dialect,
                           pred_dialect=preds.dialect, tolerance=tolerance,
                           include_unverified=include_unverified, head=head,
                           include_expected=include_expected)
               for it in golden.items]
    regressions, improvements = _baseline_diff(records, baseline) if baseline else ([], [])
    return {
        "schema_version": "1",
        "run": {"golden": golden_path, "predictions": preds_path, "run_name": preds.run_name,
                "dialect": golden.dialect, "pred_dialect": preds.dialect,
                "snapshot": golden.snapshot, "tolerance": tolerance, "tool_version": __version__},
        "summary": _summary(records),
        "by_trap": _group(records, "trap"),
        "by_level": _group(records, "level"),
        "regressions": regressions,
        "improvements": improvements,
        "warnings": _warnings(golden, preds, records, regressions, today),
        "items": records,
    }
