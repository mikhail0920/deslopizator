from dataclasses import dataclass


@dataclass(frozen=True)
class ArchitectureLayer:
    name: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class ArchitectureViolation:
    source_module: str
    target_module: str
    source_layer: str
    target_layer: str
    line: int
    rule: str

    @property
    def fingerprint(self) -> str:
        return "|".join((self.rule, self.source_module, self.target_module))


@dataclass(frozen=True)
class ArchitectureMetrics:
    violation_count: int
    violations: tuple[ArchitectureViolation, ...]


@dataclass(frozen=True)
class ArchitectureForbidden:
    source_layer: str
    target_layer: str


@dataclass(frozen=True)
class ArchitectureIndependent:
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class ArchitectureLayered:
    layers: tuple[str, ...]


@dataclass(frozen=True)
class ArchitectureConfig:
    layers: tuple[ArchitectureLayer, ...] = ()
    forbidden: tuple[ArchitectureForbidden, ...] = ()
    independent: tuple[ArchitectureIndependent, ...] = ()
    layered: tuple[ArchitectureLayered, ...] = ()
