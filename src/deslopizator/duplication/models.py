from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedToken:
    value: str
    line: int
    column: int


@dataclass(frozen=True)
class CloneInstance:
    path: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class CloneGroup:
    token_count: int
    instances: tuple[CloneInstance, ...]
    fingerprint: str = ""


@dataclass(frozen=True)
class DuplicationMetrics:
    clone_group_count: int
    clone_instance_count: int
    duplicated_lines: int
    production_sloc: int
    duplication_density: float
