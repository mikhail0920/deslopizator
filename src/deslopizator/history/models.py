from dataclasses import dataclass


@dataclass(frozen=True)
class FileChurn:
    path: str
    commits_90d: int
    commits_180d: int
    commits_365d: int
    authors_180d: int
    added_lines_180d: int
    deleted_lines_180d: int


@dataclass(frozen=True)
class FileStructuralDebt:
    path: str
    eroded_mass: float
    eroded_function_count: int
    duplicated_lines_in_file: int
    clone_instances_in_file: int
    participates_in_runtime_cycle: bool
    structural_debt: float


@dataclass(frozen=True)
class Hotspot:
    path: str
    structural_debt: float
    churn: int
    priority: float
