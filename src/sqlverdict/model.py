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
