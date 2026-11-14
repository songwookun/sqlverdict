import re
from dataclasses import dataclass
from datetime import date

from sqlverdict.hints import _SELECT_STAR

LEVELS = ("L1", "L2", "L3", "L4")
TRAPS = ("dup_join", "unique_id", "biz_term", "empty_ok", "none")
STALE_DAYS = 30


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warn"
    id: str | None
    message: str


def _item_issues(it):
    out = []

    def err(m):
        out.append(Issue("error", it.id, m))

    def warn(m):
        out.append(Issue("warn", it.id, m))

    if it.problem:
        err(f"형식 오류로 채점할 수 없습니다: {it.problem}")
    if not it.question:
        err("question이 없습니다")
    if it.level not in LEVELS:
        err(f"level은 {'/'.join(LEVELS)} 중 하나여야 합니다")
    if it.trap not in TRAPS:
        err(f"trap은 {'/'.join(TRAPS)} 중 하나여야 합니다")
    elif it.trap != "none" and not it.why:
        err("trap이 있으면 why가 필요합니다 (사람이 이것만 읽고 검증)")
    if not it.verified:
        warn("verified: false — 사람이 확인하기 전까지 채점에서 제외됩니다")
    if it.expected and not it.expected.rows and not it.empty_ok:
        warn("정답이 빈 결과입니다. 의도한 것이면 empty_ok: true")
    return out


_VOLATILE = re.compile(
    r"\b(now|curdate|curtime|sysdate|systimestamp|getdate|random|rand|uuid|newid|"
    r"current_date|current_time|current_timestamp|localtimestamp)\b", re.IGNORECASE)

_OPEN_PERIOD = re.compile(
    r"최근|오늘|어제|올해|금년|작년|지금|현재|"
    r"이번\s*(주|달|월|분기|해)|지난\s*(주|달|월|분기|해)|"
    r"\b(recent(ly)?|today|yesterday|current(ly)?|"
    r"(this|last)\s+(week|month|quarter|year))\b", re.IGNORECASE)


def _text_issues(it):
    out = []
    if it.gold_sql:
        if _SELECT_STAR.search(it.gold_sql):
            out.append(Issue("warn", it.id, "gold_sql에 SELECT *: 필요한 컬럼만 고르세요"))
        m = _VOLATILE.search(it.gold_sql)
        if m:
            out.append(Issue("warn", it.id,
                             f"gold_sql에 시간·난수 함수 {m.group(1)}: 뽑을 때마다 정답이 바뀝니다"))
    if it.question:
        m = _OPEN_PERIOD.search(it.question)
        if m:
            out.append(Issue("warn", it.id,
                             f"질문에 열린 기간 표현 '{m.group(0)}': '2018년'처럼 닫힌 과거 기간을 권장합니다 (정답이 금방 낡음)"))
    return out


def _set_issues(golden, today):
    out = []
    seen = set()
    for it in golden.items:
        if it.id in seen:
            out.append(Issue("error", it.id, "id가 중복됩니다"))
        seen.add(it.id)
    if not golden.items:
        return out + [Issue("warn", None, "문항이 없습니다")]

    if {it.trap for it in golden.items} <= {"none", None}:
        out.append(Issue("warn", None, "함정 문항이 없습니다: 쉬운 문항만으로는 silent_wrong을 잡지 못합니다"))
    levels = {it.level for it in golden.items if it.level in LEVELS}
    if len(levels) == 1:
        out.append(Issue("warn", None, f"난이도가 {levels.pop()} 하나뿐입니다: 점수가 부풀려질 수 있습니다"))

    if golden.snapshot is None:
        out.append(Issue("warn", None, "snapshot이 없습니다: 정답이 낡았는지 판단할 기준이 없습니다"))
    else:
        try:
            age = (today - date.fromisoformat(golden.snapshot)).days
        except ValueError:
            out.append(Issue("warn", None, "snapshot은 YYYY-MM-DD 형식이어야 합니다"))
        else:
            if age > STALE_DAYS:
                out.append(Issue("warn", None, f"snapshot이 {age}일 지났습니다: 정답 다시 뽑기를 권장합니다"))
    return out


def _pred_issues(golden, preds):
    out = []
    gold_ids = {it.id for it in golden.items}
    seen = set()
    for p in preds.items:
        if p.id in seen:
            out.append(Issue("error", p.id, "예측 id가 중복됩니다"))
        seen.add(p.id)
        if p.id not in gold_ids:
            out.append(Issue("error", p.id, "골든셋에 없는 id입니다"))
        if p.problem:
            out.append(Issue("error", p.id, f"예측 형식 오류: {p.problem}"))
    for it in golden.items:
        if it.id not in seen:
            out.append(Issue("warn", it.id, "예측이 없습니다 (missing_prediction)"))
    return out


def check(golden, preds=None, today=None):
    today = today or date.today()
    out = _set_issues(golden, today)
    for it in golden.items:
        out += _item_issues(it) + _text_issues(it)
    if preds is not None:
        out += _pred_issues(golden, preds)
    return out
