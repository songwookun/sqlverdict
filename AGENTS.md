# AGENTS.md — sqlverdict 저장소 작업 지침

Text-to-SQL 결과를 규칙으로 채점하는 라이브러리. 사용법은 README.md.
(`sqlverdict init`이 사용자 프로젝트에 만드는 `evals/AGENTS.md`는 `src/sqlverdict/templates/AGENTS.md`이며 이 파일과 별개다.)

## 명령
- 설치: `uv sync`
- 테스트: `uv run pytest` (DB 없이, 기본에서 `db` 마커 제외)
- 실제 DB 테스트: `docker compose -f tests/db/docker-compose.yml up -d --wait` → `uv sync --group db` → `uv run pytest -m db`
- 드라이버 반환 타입 확인: `uv run python tests/db/probe.py [mysql] [postgresql] [oracle]`

## 구조
- `normalize.py` DB별 값 → 표준형 / `compare.py` 판정·`to_result` / `hints.py` 차이 → 힌트 문장
- `loader.py` YAML 읽기·형식 검증 / `check.py` 골든셋 원칙 검사 / `score.py` 전체 채점 → 보고서 dict
- `output/` table·json·html / `cli.py` init·check·score / `templates/` init이 복사하는 파일

## 지켜야 할 원칙
1. **false correct가 가장 나쁘다.** 틀린 답을 맞다고 하는 변경(값 버리기, 너그러운 비교, 값으로 컬럼 찾기)은 하지 않는다. 애매하면 틀린 쪽(드러나는 쪽)으로.
2. **런타임 의존성은 pyyaml 하나.** DB 드라이버·numpy·jinja 등을 런타임에 추가하지 않는다.
3. **DB·네트워크에 접속하지 않는다.** SQL 실행은 사용자 몫. `to_result`도 실행하지 않는다.
4. **결과 값은 기본 출력에 넣지 않는다.** 힌트 문장에도 값을 넣지 않는다 (`test_hints_never_contain_values`).
5. **HTML은 모든 값을 `esc()`로.** CSP(`default-src 'none'`)를 풀지 않는다.
6. **JSON 출력은 `schema_version` 봉투.** 필드 추가는 되지만 이름 변경·삭제는 하지 않는다.
7. **종료 코드**: 0 정상 / 1 `--fail-on`·check error / 2 입력 오류. 보고서를 먼저 쓰고 종료 코드를 정한다.
8. 메시지·템플릿은 한국어. 사용자 입력 오류는 트레이스백 대신 `InputError` → 한 줄 메시지.

## 변경할 때
- normalize 규칙을 바꾸면 `tests/test_normalize.py`와 `tests/db/test_real_drivers.py`의 `SAME`/`PER_DB` 표를 함께 고치고, README "DB별 값 처리 규칙"·"알려진 한계"도 맞춘다.
- 템플릿을 바꾸면 `tests/test_cli.py`의 데모 판정 개수 테스트를 확인한다.
- 판정·힌트 문구를 바꾸면 README 예시 출력도 다시 뽑는다.
- 커밋 메시지는 `모듈: 무엇을 (왜)` 형식, 한국어.
