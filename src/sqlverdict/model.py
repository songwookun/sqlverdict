from dataclasses import dataclass, field


@dataclass(frozen=True)
class Result:
    columns: list[str]
    rows: list[tuple]


@dataclass
class Verdict:
    label: str
    detail: dict = field(default_factory=dict)
    hints: list[str] = field(default_factory=list)


@dataclass
class GoldenItem:
    id: str
    question: str | None
    expected: Result | None
    level: str | None = None
    trap: str | None = None
    why: str | None = None
    verified: bool = False
    ordered: bool = False
    compare_columns: list[str] | None = None
    allow_extra_columns: bool = False
    tolerance: float | None = None
    empty_ok: bool = False
    gold_sql: str | None = None
    problem: str | None = None


@dataclass
class Golden:
    dialect: str
    snapshot: str | None
    items: list[GoldenItem]


@dataclass
class PredItem:
    id: str
    result: Result | None = None
    error: str | None = None
    pred_sql: str | None = None
    problem: str | None = None


@dataclass
class Predictions:
    run_name: str | None
    dialect: str | None
    items: list[PredItem]
