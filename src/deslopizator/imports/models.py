from dataclasses import dataclass


@dataclass(frozen=True)
class ImportEdge:
    source: str
    target: str
    line: int
    kind: str


@dataclass(frozen=True)
class UnresolvedImport:
    source: str
    raw_import: str
    line: int


@dataclass(frozen=True)
class ImportCycle:
    modules: tuple[str, ...]


@dataclass(frozen=True)
class ImportMetrics:
    internal_module_count: int
    runtime_edge_count: int
    type_checking_edge_count: int
    cycle_group_count: int
    modules_in_cycles: int
    cycle_density: float
    unresolved_import_count: int
    cycles: tuple[ImportCycle, ...] = ()


@dataclass(frozen=True)
class ImportAnalysis:
    edges: tuple[ImportEdge, ...]
    unresolved: tuple[UnresolvedImport, ...]
    cycles: tuple[ImportCycle, ...]
    metrics: ImportMetrics
    errors: tuple[str, ...] = ()
