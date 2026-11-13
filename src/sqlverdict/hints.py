import re

_SELECT_STAR = re.compile(r"select\s+(distinct\s+)?\*", re.IGNORECASE)


def build_hints(label, detail, pred_sql=None):
    hints = []
    er, gr = detail.get("expected_rows"), detail.get("got_rows")
    if label == "silent_wrong" and er and gr and gr > er and gr % er == 0:
        hints.append(f"행 수가 정확히 {gr // er}배: 중복 조인 의심")
    if label == "silent_wrong" and er and gr == 0:
        hints.append("결과가 비어 있음: WHERE 조건이나 조인 키 불일치 의심")
    if "ratio" in detail:
        r = detail["ratio"]
        hints.append(f"값이 정확히 {r:g}배: " + ("중복 조인 의심" if r > 1 else "필터 누락·기간 차이 의심"))
    if detail.get("missing_columns"):
        hints.append("필요한 컬럼이 없음: " + ", ".join(detail["missing_columns"]))
    if detail.get("matched_by") == "position":
        hints.append("이름이 달라 위치로 비교함: 컬럼 이름을 맞추거나 compare_columns 지정 권장")
    if label == "extra_columns":
        hints.append("필요 없는 컬럼 포함: " + ", ".join(detail.get("extra_columns", [])))
    if pred_sql and _SELECT_STAR.search(pred_sql):
        hints.append("SELECT * 사용: 필요한 컬럼만 고르세요")
    return hints
