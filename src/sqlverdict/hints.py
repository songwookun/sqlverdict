import re

_SELECT_STAR = re.compile(r"select\s+(distinct\s+)?\*", re.IGNORECASE)


def _simple_multiple(r):
    if r <= 0:
        return False
    for x in (r, 1 / r):
        n = round(x)
        if n >= 2 and abs(x - n) <= 1e-5 * n:
            return True
    return False


def _ratio_hint(r):
    if r == 0:
        return "값이 0으로 나옴: 조건 과다·INNER JOIN으로 행 누락 의심"
    if r in (100, 0.01):
        return f"값이 정확히 {r:g}배: 비율 단위 차이(% vs 0~1) 의심"
    if _simple_multiple(r):
        cause = "중복 조인·필터 누락 의심" if r > 1 else "조건 과다·INNER JOIN으로 행 누락 의심"
        return f"값이 정확히 {r:g}배: {cause}"
    return f"값이 약 {r:.3g}배: 집계 대상·계산식·조건 차이 의심"


def build_hints(label, detail, pred_sql=None):
    hints = []
    er, gr = detail.get("expected_rows"), detail.get("got_rows")
    if label == "silent_wrong" and er and gr and gr > er and gr % er == 0:
        hints.append(f"행 수가 정확히 {gr // er}배: 중복 조인 의심")
    if label == "silent_wrong" and er and gr == 0:
        hints.append("결과가 비어 있음: WHERE 조건이나 조인 키 불일치 의심")
    if "ratio" in detail:
        hints.append(_ratio_hint(detail["ratio"]))
    if detail.get("missing_columns"):
        hints.append("필요한 컬럼이 없음: " + ", ".join(detail["missing_columns"]))
    if detail.get("matched_by") == "position":
        hints.append("이름이 달라 위치로 비교함: 컬럼 이름을 맞추거나 compare_columns 지정 권장")
    if label == "correct_approx":
        hints.append("허용 오차 안에서만 같음: 반올림·자료형(FLOAT/DECIMAL) 차이 의심")
    if detail.get("extra_columns"):
        hints.append("필요 없는 컬럼 포함: " + ", ".join(detail.get("extra_columns", [])))
    if pred_sql and _SELECT_STAR.search(pred_sql):
        hints.append("SELECT * 사용: 필요한 컬럼만 고르세요")
    return hints
