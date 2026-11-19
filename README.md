# sqlverdict

Text-to-SQL 결과를 규칙으로 채점하고, 어디를 고쳐야 하는지 알려주는 오픈소스 라이브러리.
에러 없이 실행되지만 결과가 틀린 SQL(silent_wrong)을 잡는 것이 목표다.

- **무료**: `pip install sqlverdict`로 바로 쓰고, 서버나 API 비용이 없다.
- **LLM 없이 채점**: 판정은 규칙이라 같은 결과를 넣으면 항상 같은 판정이 나온다.
- **AI와 쓰면 더 빠르게**: AI가 골든셋 초안을 만들고 결과를 읽어 고칠 곳을 찾는다. 정답 확정은 사람이 한다.

> **English summary** — sqlverdict is a rule-based scorer for Text-to-SQL results.
> It compares the result set produced by your model's SQL with a verified golden result
> (SQLite / MySQL / PostgreSQL / Oracle) and flags *silent_wrong* answers:
> queries that run without error but return wrong numbers, such as a duplicate join that triples a count.
> No LLM and no server: verdicts are deterministic and come with fix hints.
> CLI messages and docs are currently in Korean.

## silent_wrong이란

질문: "2024년에 주문한 고객은 몇 명?"

| | SQL | 결과 |
|---|---|---|
| 정답 | `SELECT COUNT(DISTINCT customer_id) FROM orders WHERE …` | 312 |
| 예측 | `SELECT COUNT(o.customer_id) FROM orders o JOIN order_items i ON … WHERE …` | 936 |

에러도 없고 숫자도 그럴듯하다. 실행 성공률만 보면 맞은 것으로 집계된다.
sqlverdict는 이것을 `silent_wrong`으로 판정하고 `값이 정확히 3배: 중복 조인·필터 누락 의심`이라고 알려준다.

## 설치

```bash
pip install sqlverdict
```

Python 3.10 이상. 런타임 의존성은 PyYAML 하나다.
**sqlverdict는 DB에 접속하지 않는다.** SQL 실행은 사용자 쪽에서 하고, 그 결과만 받아 채점한다.

## 빠른 시작

```bash
sqlverdict init          # evals/ 에 예시 golden.yaml · predictions.yaml · AGENTS.md 생성
sqlverdict check evals/golden.yaml evals/predictions.yaml
sqlverdict score evals/golden.yaml evals/predictions.yaml
```

```
정확도 40.0%  (correct 2 / 채점 5 / 전체 6)
판정  correct 2 · correct_approx 1 · extra_columns 0 · silent_wrong 1 · error 1
제외  skipped_unverified 1 · unscorable 0 · missing_prediction 0
…
id    판정            level  trap       질문                            안내
Q002  silent_wrong    L2     dup_join   2024년에 주문한 고객은 몇 명?   값이 정확히 3배: 중복 조인·필터 누락 의심
Q003  error           L3     unique_id  2024년 매출 상위 3명 고객의 i…  실행 실패: no such column: c.nm
Q004  correct_approx  L3     biz_term   2024년 활성 고객의 평균 주문 …  허용 오차 안에서만 같음: 반올림·자료형(FLOAT/DECIMAL) 차이 의심
```

예시의 숫자는 가상 데이터다. 실제로 쓰려면:

1. `golden.yaml`의 질문을 우리 DB에 맞게 바꾸고, `gold_sql`을 실행해 `expected`를 채운다. `snapshot`은 그날 날짜로 적는다.
2. 예시 문항은 `verified: true`로 되어 있다. 사람이 확인한 문항만 true로 두고, 나머지는 false로 바꾼다.
3. Text-to-SQL이 만든 SQL을 실행해 결과를 `predictions.yaml`에 적는다. 또는 [파이썬 API](#파이썬-api)로 바로 비교한다.
4. `check` → `score`

## 판정

| 판정 | 뜻 | 예 | 정확도에 포함 |
|---|---|---|---|
| `correct` | 계산 오차(1e-9)만 빼고 같음 | 조건 표현은 달라도 같은 건수 | O |
| `correct_approx` | 허용 오차(기본 0.1%) 안에서만 같음 | 평균 152340.3333 vs 152340.33 | 따로 표시 |
| `extra_columns` | 정답 컬럼 값은 같지만 필요 없는 컬럼까지 가져옴 | `SELECT *`로 20개 컬럼 | X |
| `silent_wrong` | 실행됐는데 결과가 다름 | 중복 조인으로 건수가 3배 | X |
| `error` | 사용자 쪽 실행이 실패함 | 없는 컬럼 이름 | X |

정확도 = `correct` ÷ 채점한 문항. 반올림 비교를 쓰는 다른 도구와 견줄 때는 `correct + correct_approx`를 보면 된다.

채점하지 않은 문항은 판정이 아니라 **상태**로 따로 센다.

| 상태 | 뜻 |
|---|---|
| `skipped_unverified` | `verified: false` — 사람이 확인하기 전 (`--include-unverified`로 포함) |
| `unscorable` | 골든셋·예측 형식 오류로 비교 불가 (사유가 함께 나옴) |
| `missing_prediction` | 이 문항의 예측이 없음 |

### 비교 규칙
- **컬럼 매칭**: 이름이 같으면(대소문자 무시) 그 컬럼끼리, 다르면 위치로(1번째↔1번째). 값이 비슷한 컬럼을 찾아다니지 않는다 — 우연히 같은 값이 맞은 것으로 잡히지 않게.
- **행 순서**: 기본은 정렬한 뒤 비교. `ordered: true` 문항만 순서까지 본다.
- **컬럼 수**: 예측이 더 많으면 `extra_columns`(정답으로 치지 않음, Spider·BIRD 관례). 필요한 컬럼이 없으면 `silent_wrong`.

## 파일 형식

골든셋은 고정하고, 예측은 실행(프롬프트 버전 등)마다 따로 쌓는다. 둘은 `id`로 짝을 맞춘다.

### 골든셋 `golden.yaml`

```yaml
dialect: mysql            # sqlite | mysql | postgresql | oracle
snapshot: 2026-11-13      # 정답을 DB에서 뽑은 날짜 (30일 지나면 경고)
items:
  - id: q007
    question: 2018년 고객별 주문 건수 상위 5명은?
    level: L4
    trap: dup_join
    why: orders와 order_items를 조인하면 주문이 상품 수만큼 늘어남
    verified: true
    ordered: true
    gold_sql: SELECT customer_id, COUNT(*) AS order_count FROM orders WHERE …
    expected:
      columns: [customer_id, order_count]
      rows: [[A, 12], [B, 9], [C, 7], [D, 6], [E, 5]]
  - id: q008
    question: 2018년 주문이 가장 많은 날짜는?
    level: L2
    trap: none
    verified: true
    expected: {columns: [order_date], rows: [[2018-11-23]]}
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `id`, `question`, `level`, `trap`, `expected` | O | `level`은 L1~L4, `trap`은 dup_join / unique_id / biz_term / empty_ok / none |
| `why` | trap≠none이면 O | 무엇을 시험하는지 + 정답 근거. 사람은 이것만 읽고 검증 |
| `verified` | | 기본 false (채점 제외) |
| `ordered` | | 행 순서까지 비교 |
| `compare_columns` | | 이 컬럼만 비교 |
| `allow_extra_columns` | | 예측의 추가 컬럼 허용 |
| `tolerance` | | 이 문항의 허용 오차 (상대값, 0이면 엄격 비교만) |
| `empty_ok` | | 빈 결과가 정답 |
| `gold_sql` | | 정답 SQL. 실행하지 않고 `check`의 검사·다시 뽑기용 |

작성 규칙(함정 섞기, 닫힌 과거 기간만 묻기 등)은 `init`이 만드는 `evals/AGENTS.md`에 있고, 기계로 확인 가능한 것은 `check`가 검사한다.

### 예측 `predictions.yaml`

```yaml
run_name: prompt-v2
dialect: postgresql       # 선택: 안 적으면 골든셋 dialect (DB 마이그레이션 검증 때만)
items:
  - id: q007
    pred_sql: SELECT …    # 선택: SELECT * 같은 힌트용
    result:
      columns: [customer_id, cnt]
      rows: [[A, 24], [B, 18], [C, 14], [D, 12], [E, 10]]
  - id: q008
    error: "Unknown column 'order_dt'"   # 실행 실패면 result 대신
```

> **날짜는 따옴표 없이** 쓴다. `2024-01-01`은 날짜로 읽혀 DB별 규칙을 타지만, `"2024-01-01"`은 그냥 문자열이다.
> 에러 메시지처럼 `: `가 들어간 값은 따옴표로 감싼다.

## CLI

```bash
sqlverdict init [폴더]                                   # 기본 evals/. 파일이 있으면 중단 (--force로 덮어쓰기)
sqlverdict check golden.yaml [predictions.yaml] [--format table|json]
sqlverdict score golden.yaml predictions.yaml [옵션]
```

| score 옵션 | 설명 |
|---|---|
| `--format table\|json\|html` | 기본 table (터미널 표) |
| `-o 경로` | 파일로 저장. 없으면 화면(stdout) 출력 |
| `--tolerance 0.001` | 전체 허용 오차 (상대값, 0.001 = 0.1%) |
| `--baseline 이전.json` | 이전 실행과 비교: 새로 틀린 문항 / 새로 맞은 문항 |
| `--fail-on 판정` | 해당 판정·상태가 하나라도 있으면 종료 코드 1. 반복 가능 |
| `--head N` | 예측 결과 값을 N행까지 포함 (기본 0) |
| `--include-expected` | 정답 결과 값 포함 (디버깅용) |
| `--include-unverified` | `verified: false` 문항도 채점 |

**종료 코드**: `0` 정상 · `1` `--fail-on`에 걸림 또는 `check` error · `2` 입력 오류(파일 없음, YAML 형식, 잘못된 옵션)

### 이전 실행과 비교

```bash
sqlverdict score golden.yaml preds_v1.yaml --format json -o v1.json
sqlverdict score golden.yaml preds_v2.yaml --baseline v1.json
```

이전에 맞던 문항이 한꺼번에 여러 개 틀리면, SQL 문제가 아니라 DB 데이터가 바뀌어 정답이 낡았을 수 있다는 경고가 나온다.

### CI에서 배포 막기 (GitHub Actions 예)

```yaml
- run: pip install sqlverdict
- run: python scripts/run_text2sql.py --out evals/predictions.yaml   # 우리 Text-to-SQL 실행 (사용자 코드)
- run: sqlverdict check evals/golden.yaml evals/predictions.yaml
- run: sqlverdict score evals/golden.yaml evals/predictions.yaml --fail-on silent_wrong --fail-on error --format html -o report.html
- uses: actions/upload-artifact@v7
  if: always()
  with: {name: sqlverdict-report, path: report.html}
```

보고서를 먼저 쓴 뒤 종료 코드를 정하므로, 실패한 실행에서도 `report.html`이 남는다.

## 파이썬 API

DB 드라이버가 준 값을 그대로 넘기면 Decimal·날짜 객체가 원래 모양으로 들어와 정규화가 가장 정확하다.

```python
from sqlverdict import compare, to_result

cur.execute(gold_sql)
expected = to_result(cur)          # DB-API 커서 → Result (실행은 하지 않음, 남은 행을 모두 읽음)
cur.execute(pred_sql)
got = to_result(cur)

v = compare(expected, got, dialect="mysql", pred_sql=pred_sql)
v.label    # 'silent_wrong'
v.detail   # {'expected_rows': 2, 'got_rows': 2, 'matched_by': 'position',
           #  'column_map': {'order_count': 'cnt'}, 'differing_columns': ['order_count'], 'ratio': 2.0}
v.hints    # ['값이 정확히 2배: 중복 조인·필터 누락 의심',
           #  '이름이 달라 위치로 비교함: 컬럼 이름을 맞추거나 compare_columns 지정 권장']
```

- `{"columns": [...], "rows": [[...]]}` 형태의 dict도 그대로 넘길 수 있다.
- DB 마이그레이션 검증처럼 정답과 예측의 DB가 다르면 `expected_dialect="mysql", got_dialect="postgresql"`.
- 그 밖의 인자: `ordered`, `compare_columns`, `allow_extra_columns`, `tolerance` (골든셋 필드와 같은 뜻).

## DB별 값 처리 규칙

정답과 예측의 값을 DB마다 하나의 표준형으로 바꾼 뒤 비교한다.
아래 규칙은 MySQL 8.4 · PostgreSQL 17 · Oracle 23ai Free에서 pymysql · psycopg 3 · python-oracledb(thin)로 확인했다.

| 값 | 표준형 |
|---|---|
| 숫자 (Decimal · float · bool) | 정수로 떨어지면 int, 아니면 float. true/false → 1/0 |
| 날짜 | `2024-01-01`. 시간대 없는 자정 datetime(Oracle DATE)도 날짜로 |
| 날짜+시각 | `2024-01-01 12:00:00.5` (소수 초는 0이 아니면 유지) |
| 시간대 있는 시각 | UTC로 바꿔 `2024-01-01 03:00:00+00:00`. 시간대 없는 값과는 다르게 본다 |
| 시각 (PG TIME · MySQL TIME) | `12:30:00` |
| 기간 (INTERVAL) | 파이썬 timedelta 표기 (`1 day, 0:00:00`) |
| UUID · JSON · 배열 | 문자열. JSON은 키를 정렬 |
| NaN | `'NaN'` (NaN끼리 같고, NULL과는 다름) |
| Oracle 빈 문자열 | NULL (Oracle은 `''`를 NULL로 저장) |

## 알려진 한계

틀린 답을 맞다고 하는 쪽(false correct)은 막았다. 남은 것은 대부분 **맞는 답이 틀렸다고 나오는 쪽**이라 판정에 드러나고, SQL에서 맞추면 된다. 마지막 두 줄은 판정 밖의 한계다.

- **CHAR(n) 공백**: PostgreSQL · Oracle은 `'A  '`처럼 공백을 채워 준다 → `RTRIM` 사용
- **Oracle TIMESTAMP WITH TIME ZONE**: python-oracledb thin 모드는 시간대를 버리고 준다 → `SYS_EXTRACT_UTC(col)`로 뽑기
- **단정밀도 실수 교차 비교**: MySQL FLOAT · Oracle BINARY_FLOAT와 다른 DB를 비교하면 `correct_approx`
- **JSON 교차 비교**: MySQL은 JSON 키를 자체 순서로 내보내 PostgreSQL과 문자열이 다를 수 있다
- **문자열로 온 값은 그대로**: 대문자 UUID 문자열, YAML에서 따옴표 친 날짜는 변환하지 않는다
- **시간대 있는 TIME(timetz)**: 시간대를 무시한다
- **허용 오차 안의 값끼리** 정렬 순서가 뒤바뀌면 다른 행끼리 비교될 수 있다 (근사값이 많은 비정렬 문항)
- `SELECT *` 힌트는 정규식이라 주석 안의 `SELECT *`도 잡는다 (판정에는 영향 없음)
- 기계로 못 잡는 것은 사람이 확인: 상위 N 문항의 경계 동점, 질문의 애매함, `gold_sql`을 고친 뒤 `verified`를 false로 되돌리기

## 데이터와 보안

- **결과 값은 기본으로 보고서에 나오지 않는다.** 정답 값은 AI가 보면 답을 외워 점수만 올리고(시험 문제 유출), 예측 값에는 고객 정보 같은 실무 데이터가 섞인다. `--head`, `--include-expected`로 켠 보고서는 공유에 주의.
- **예측 `error` 메시지는 300자까지 보고서에 포함된다.** DB 에러 메시지에 값이 섞일 수 있다.
- **예측을 만드는 쪽이 `golden.yaml`을 읽지 못하게 한다.** `expected`와 `gold_sql`이 그대로 들어 있다.
- HTML 보고서는 단일 파일이고, 모든 값을 이스케이프하며 CSP로 스크립트·외부 자원을 막는다.
- sqlverdict는 DB나 네트워크에 접속하지 않는다.

## 개발

```bash
uv sync
uv run pytest                                              # 기본 (DB 없이)

docker compose -f tests/db/docker-compose.yml up -d --wait # MySQL + PostgreSQL
uv sync --group db
uv run pytest -m db                                        # 실제 드라이버 값 테스트
uv run python tests/db/probe.py                            # 드라이버가 주는 타입 보기
docker compose -f tests/db/docker-compose.yml --profile oracle down
```

Oracle은 메모리 때문에 따로 띄운다: `docker compose -f tests/db/docker-compose.yml --profile oracle up -d --wait oracle`, `pytest -m db`에서 접속할 수 없는 DB는 건너뛴다.

## 라이선스

MIT
