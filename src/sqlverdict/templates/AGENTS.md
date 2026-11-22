# 골든셋 작성 규칙 (sqlverdict)

이 폴더의 golden.yaml은 Text-to-SQL 채점 기준이다. 정답이 틀리면 채점 전체가 틀린다.
AI 에이전트는 이 폴더에서 작업할 때 아래 규칙을 그대로 따른다.

## 작업 순서 (이 폴더에서 실행)
1. 문항은 닫힌 과거 기간으로 쓴다 ("최근 30일" X → "2024년" O)
2. 채점 전에 gold_sql을 실행해 expected를 갱신하고 snapshot을 그날 날짜로 바꾼다
3. `sqlverdict check golden.yaml predictions.yaml --format json` → `summary.error`가 0이 될 때까지 issues를 고친다
4. `sqlverdict score golden.yaml predictions.yaml --format json`
5. warnings가 있으면 2번부터 다시

## 규칙
- AI가 추가하거나 고친 문항은 반드시 `verified: false`. true로 바꾸는 건 사람만 한다
- gold_sql을 고치면 verified를 false로 되돌린다
- 함정 문항을 섞는다: dup_join(중복 조인), unique_id(동명이인 등 식별자), biz_term(사내 용어 정의), empty_ok(빈 결과가 정답)
- trap이 none이 아니면 why에 "무엇을 시험하는지 + 정답 근거"를 쓴다. 사람은 why만 읽고 검증한다
- 난이도(L1~L4)를 고르게 섞는다
- 빈 결과가 정답이면 `empty_ok: true`
- id는 중복 금지. 예측 id는 골든셋 id와 같아야 한다
- gold_sql은 필요한 컬럼만 (SELECT * 금지), NOW()·RANDOM() 같은 함수 금지
- 상위 N 문항은 N번째와 N+1번째가 동점이 아니어야 한다
- 질문은 사람마다 다른 답이 나오지 않게 구체적으로 쓴다

## 하지 말 것
- 예측 SQL을 만들 때 golden.yaml의 expected·gold_sql을 보지 않는다 (시험 문제 유출)
- 예측을 맞추려고 expected를 고치지 않는다
- `--include-expected`, `--head`로 정답·결과 값을 보고서에 넣어 공유하지 않는다 (정답 유출·실무 데이터 노출)

## 필드
| 필드 | 필수 | 설명 |
|---|---|---|
| id, question, level, trap, expected | O | expected = {columns, rows} |
| why | trap≠none이면 O | 검증 근거 |
| verified | | 기본 false (채점 제외) |
| ordered | | 행 순서까지 비교 (ORDER BY 문항) |
| compare_columns | | 이 컬럼만 비교 |
| allow_extra_columns | | 예측의 추가 컬럼 허용 |
| tolerance | | 이 문항의 상대 오차 (기본 0.001 = 0.1%) |
| empty_ok | | 빈 결과가 정답. 정답·예측 모두 0행이면, 정답 컬럼이 (이름 또는 위치로) 모두 대응될 때 정답 (추가 컬럼은 힌트로만) |
| gold_sql | | 정답 SQL (다시 뽑기·검사용) |
