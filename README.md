# sqlverdict

**English** · [한국어](https://github.com/songwookun/sqlverdict/blob/main/README.ko.md)

[![ci](https://github.com/songwookun/sqlverdict/actions/workflows/ci.yml/badge.svg)](https://github.com/songwookun/sqlverdict/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sqlverdict)](https://pypi.org/project/sqlverdict/)
[![Python](https://img.shields.io/pypi/pyversions/sqlverdict)](https://pypi.org/project/sqlverdict/)
[![License](https://img.shields.io/github/license/songwookun/sqlverdict)](https://github.com/songwookun/sqlverdict/blob/main/LICENSE)

An open-source library that scores Text-to-SQL results with rules and tells you where to fix them.
Its goal is to catch SQL that runs without error but returns the wrong result (**silent_wrong**).

- **Free**: `pip install sqlverdict` and go. No server, no API costs.
- **No LLM in the loop**: verdicts are rule-based, so the same results always get the same verdict.
- **Faster with AI**: an AI can draft the golden set and read the report to find what to fix. A human confirms the answers.

> CLI messages, hints and templates are currently in Korean. Verdict names, JSON keys and options are English.

## What is silent_wrong?

Question: "How many customers placed an order in 2024?"

| | SQL | Result |
|---|---|---|
| Golden | `SELECT COUNT(DISTINCT customer_id) FROM orders WHERE …` | 312 |
| Prediction | `SELECT COUNT(o.customer_id) FROM orders o JOIN order_items i ON … WHERE …` | 936 |

No error, and the number looks plausible. If you only measure execution success, it counts as a pass.
sqlverdict marks it `silent_wrong` and adds a hint: the value is exactly 3× — suspect a duplicate join or a missing filter.

## Install

```bash
pip install sqlverdict
```

Python 3.10+. The only runtime dependency is PyYAML.
**sqlverdict never connects to your database.** You run the SQL; sqlverdict only scores the results.

## Quick start

```bash
sqlverdict init          # creates example golden.yaml · predictions.yaml · AGENTS.md in evals/
sqlverdict check evals/golden.yaml evals/predictions.yaml
sqlverdict score evals/golden.yaml evals/predictions.yaml
```

Output (messages are in Korean — 정확도 = accuracy, 판정 = verdicts, 제외 = excluded, 안내 = hint):

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

The example numbers are made up. To use it for real:

1. Rewrite the questions in `golden.yaml` for your database, run each `gold_sql` to fill in `expected`, and set `snapshot` to that day's date.
2. The example items are marked `verified: true`. Keep `true` only for items a human has checked; set the rest to `false`.
3. Run the SQL your Text-to-SQL system produced and write the results to `predictions.yaml` — or compare directly with the [Python API](#python-api).
4. `check` → `score`

## Verdicts

| Verdict | Meaning | Example | Counts as correct |
|---|---|---|---|
| `correct` | Equal up to floating-point noise (1e-9) | Different WHERE wording, same count | Yes |
| `correct_approx` | Equal only within tolerance (default 0.1%) | Average 152340.3333 vs 152340.33 | Reported separately |
| `extra_columns` | Required columns match, but extra columns were returned | 20 columns from `SELECT *` | No |
| `silent_wrong` | Ran fine, result differs | Count tripled by a duplicate join | No |
| `error` | Execution failed on your side | Unknown column name | No |

Accuracy = `correct` ÷ scored items. To compare with tools that round before comparing, look at `correct + correct_approx`.

Items that were not scored get a **status** instead of a verdict:

| Status | Meaning |
|---|---|
| `skipped_unverified` | `verified: false` — not yet checked by a human (include with `--include-unverified`) |
| `unscorable` | Golden or prediction entry is malformed (the reason is shown) |
| `missing_prediction` | No prediction for this item |

### Comparison rules
- **Column matching**: same name (case-insensitive) first, otherwise by position (1st ↔ 1st). It never hunts for a column with similar values — so a coincidental match can't pass.
- **Row order**: rows are sorted before comparing. Only `ordered: true` items compare order.
- **Column count**: more columns than needed → `extra_columns` (not counted as correct, as in Spider/BIRD). A required column missing → `silent_wrong`.

## File formats

Keep the golden set fixed and store predictions separately per run (prompt version, model, …). They are paired by `id`.

### Golden set `golden.yaml`

```yaml
dialect: mysql            # sqlite | mysql | postgresql | oracle
snapshot: 2026-11-13      # date the expected results were pulled (warning after 30 days)
items:
  - id: q007
    question: Top 5 customers by number of orders in 2018?
    level: L4
    trap: dup_join
    why: joining orders with order_items multiplies each order by its item count
    verified: true
    ordered: true
    gold_sql: SELECT customer_id, COUNT(*) AS order_count FROM orders WHERE …
    expected:
      columns: [customer_id, order_count]
      rows: [[A, 12], [B, 9], [C, 7], [D, 6], [E, 5]]
  - id: q008
    question: Which day had the most orders in 2018?
    level: L2
    trap: none
    verified: true
    expected: {columns: [order_date], rows: [[2018-11-23]]}
```

| Field | Required | Description |
|---|---|---|
| `id`, `question`, `level`, `trap`, `expected` | Yes | `level` is L1–L4; `trap` is dup_join / unique_id / biz_term / empty_ok / none |
| `why` | If trap ≠ none | What the item tests and why the answer is right. Reviewers verify from this alone |
| `verified` | | Default false (excluded from scoring) |
| `ordered` | | Compare row order too |
| `compare_columns` | | Compare only these columns |
| `allow_extra_columns` | | Allow extra columns in the prediction |
| `tolerance` | | Per-item tolerance (relative; 0 = strict only) |
| `empty_ok` | | An empty result is the correct answer |
| `gold_sql` | | The golden SQL. Never executed; used by `check` and for re-pulling answers |

Authoring rules (mix in trap items, ask only about closed past periods, …) are in the `evals/AGENTS.md` that `init` creates; `check` enforces what can be checked mechanically.

### Predictions `predictions.yaml`

```yaml
run_name: prompt-v2
dialect: postgresql       # optional: defaults to the golden dialect (set it only for DB migration checks)
items:
  - id: q007
    pred_sql: SELECT …    # optional: used for hints such as SELECT *
    result:
      columns: [customer_id, cnt]
      rows: [[A, 24], [B, 18], [C, 14], [D, 12], [E, 10]]
  - id: q008
    error: "Unknown column 'order_dt'"   # instead of result when execution failed
```

> **Write dates without quotes.** `2024-01-01` is read as a date and goes through the per-database rules; `"2024-01-01"` is just a string.
> Quote values that contain `: `, such as error messages.
> YAML aliases (`*name`, `<<: *name`) are rejected, to stop a tiny file from expanding into huge data.

## CLI

```bash
sqlverdict init [dir]                                    # default evals/. Stops if files exist (--force to overwrite)
sqlverdict check golden.yaml [predictions.yaml] [--format table|json]
sqlverdict score golden.yaml predictions.yaml [options]
```

| score option | Description |
|---|---|
| `--format table\|json\|html` | Default table (terminal) |
| `-o path` | Write to a file instead of stdout |
| `--tolerance 0.001` | Global tolerance (relative; 0.001 = 0.1%) |
| `--baseline prev.json` | Compare with a previous run: newly failing / newly passing items |
| `--fail-on VERDICT` | Exit code 1 if any item has this verdict or status. Repeatable |
| `--head N` | Include the first N rows of each prediction (default 0) |
| `--include-expected` | Include golden result values (for debugging) |
| `--include-unverified` | Also score `verified: false` items |

**Exit codes**: `0` OK · `1` `--fail-on` matched or `check` found errors · `2` input error (missing file, bad YAML, bad option)

### Compare with a previous run

```bash
sqlverdict score golden.yaml preds_v1.yaml --format json -o v1.json
sqlverdict score golden.yaml preds_v2.yaml --baseline v1.json
```

If many previously correct items fail at once, you get a warning that the golden answers may be stale because the data changed — not the SQL.

### Block a deploy in CI (GitHub Actions example)

```yaml
- run: pip install sqlverdict
- run: python scripts/run_text2sql.py --out evals/predictions.yaml   # your Text-to-SQL run (your code)
- run: sqlverdict check evals/golden.yaml evals/predictions.yaml
- run: sqlverdict score evals/golden.yaml evals/predictions.yaml --fail-on silent_wrong --fail-on error --format html -o report.html
- uses: actions/upload-artifact@v7
  if: always()
  with: {name: sqlverdict-report, path: report.html}
```

The report is written before the exit code is decided, so `report.html` exists even when the run fails.

## Python API

Passing the values your DB driver returned (Decimal, date objects, …) gives the most accurate normalization.

```python
from sqlverdict import compare, to_result

cur.execute(gold_sql)
expected = to_result(cur)          # DB-API cursor → Result (does not execute; reads the remaining rows)
cur.execute(pred_sql)
got = to_result(cur)

v = compare(expected, got, dialect="mysql", pred_sql=pred_sql)
v.label    # 'silent_wrong'
v.detail   # {'expected_rows': 2, 'got_rows': 2, 'matched_by': 'position',
           #  'column_map': {'order_count': 'cnt'}, 'differing_columns': ['order_count'], 'ratio': 2.0}
v.hints    # ['값이 정확히 2배: 중복 조인·필터 누락 의심',            (value exactly 2×: duplicate join / missing filter?)
           #  '이름이 달라 위치로 비교함: 컬럼 이름을 맞추거나 compare_columns 지정 권장']   (names differ, compared by position)
```

- A dict of the form `{"columns": [...], "rows": [[...]]}` works too.
- When the golden and prediction databases differ (e.g. migration checks): `expected_dialect="mysql", got_dialect="postgresql"`.
- Other arguments: `ordered`, `compare_columns`, `allow_extra_columns`, `tolerance` (same meaning as the golden fields).

## Per-database value rules

Values from both sides are converted to one canonical form per database before comparing.
These rules were verified on MySQL 8.4 · PostgreSQL 17 · Oracle 23ai Free with pymysql · psycopg 3 · python-oracledb (thin).

| Value | Canonical form |
|---|---|
| Numbers (Decimal · float · bool) | int if integral, otherwise float. true/false → 1/0 |
| Date | `2024-01-01`. A timezone-naive midnight datetime (Oracle DATE) also becomes a date |
| Date + time | `2024-01-01 12:00:00.5` (fractional seconds kept when non-zero) |
| Timezone-aware datetime | Converted to UTC: `2024-01-01 03:00:00+00:00`. Never equal to a naive value |
| Time (PG TIME · MySQL TIME) | `12:30:00` |
| Interval | Python timedelta notation (`1 day, 0:00:00`) |
| UUID · JSON · arrays | Strings. JSON keys are sorted |
| NaN | `'NaN'` (NaN equals NaN, but not NULL) |
| Oracle empty string | NULL (Oracle stores `''` as NULL) |

## Known limitations

False passes (wrong answers judged correct) are blocked. What remains mostly goes the other way — **a correct answer reported as wrong** — so it shows up in the verdict and you can fix it in SQL. The last two items are outside the verdict.

- **CHAR(n) padding**: PostgreSQL and Oracle return `'A  '` → use `RTRIM`
- **Oracle TIMESTAMP WITH TIME ZONE**: python-oracledb thin mode drops the timezone → select `SYS_EXTRACT_UTC(col)`
- **Single-precision floats across databases**: MySQL FLOAT or Oracle BINARY_FLOAT vs another database gives `correct_approx`
- **JSON across databases**: MySQL emits JSON keys in its own order, so the string may differ from PostgreSQL
- **Values that arrive as strings stay as-is**: uppercase UUID strings, quoted dates in YAML
- **Time with timezone (timetz)**: the timezone is ignored
- **Values within tolerance** can swap sort order, so different rows may be compared (unordered items with many approximate values)
- The `SELECT *` hint is a regex and also matches inside comments (no effect on verdicts)
- Left to humans: ties at the boundary of top-N items, ambiguous questions, resetting `verified` to false after editing `gold_sql`

## Data and security

- **Result values are not included in reports by default.** Golden values let an AI memorize answers (test leakage), and prediction values can contain production data such as customer details. Be careful sharing reports made with `--head` or `--include-expected`.
- **Prediction `error` messages are included (up to 300 characters).** Database error messages can contain values.
- **Don't let the system that generates predictions read `golden.yaml`.** It contains `expected` and `gold_sql` verbatim.
- The HTML report is a single file; every value is escaped, and a CSP blocks scripts and external resources.
- sqlverdict makes no database or network connections.

Report vulnerabilities privately — see [SECURITY.md](https://github.com/songwookun/sqlverdict/blob/main/SECURITY.md).

## Development

```bash
uv sync
uv run pytest                                              # default (no database)

docker compose -f tests/db/docker-compose.yml up -d --wait # MySQL + PostgreSQL
uv sync --group db
uv run pytest -m db                                        # real driver value tests
uv run python tests/db/probe.py                            # show the types each driver returns
docker compose -f tests/db/docker-compose.yml --profile oracle down
```

Oracle runs separately because of memory: `docker compose -f tests/db/docker-compose.yml --profile oracle up -d --wait oracle`. `pytest -m db` skips databases it cannot reach.

## License

MIT
