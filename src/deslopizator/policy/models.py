from dataclasses import dataclass
from pathlib import Path
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deslopizator.completeness.models import AuditResult

@dataclass(frozen=True)
class PolicyViolation:
    rule: str
    expected: str
    actual: str
    message: str

@dataclass(frozen=True)
class PolicyResult:
    passed: bool
    violations: tuple[PolicyViolation, ...]

def _eroded_functions(result):
    root = Path(result.inventory.root)
    return Counter(
        (Path(file.path).relative_to(root).as_posix(), function.qualified_name)
        for file in result.complexity.files
        for function in file.functions if function.eroded
    )


def _clone_groups(result):
    return Counter(group.fingerprint for group in result.clone_groups)


def _architecture_violations(result):
    architecture = getattr(result, "architecture", None)
    if architecture is None:
        return Counter()
    return Counter(violation.fingerprint for violation in architecture.violations)


@dataclass(frozen=True)
class AuditDiff:
    baseline: "AuditResult"
    current: "AuditResult"

    @property
    def score_increase(self) -> float:
        if self.baseline.score.total is None or self.current.score.total is None:
            return 0.0
        return self.current.score.total - self.baseline.score.total

    @property
    def new_eroded_functions(self) -> int:
        return sum((_eroded_functions(self.current) - _eroded_functions(self.baseline)).values())

    @property
    def density_increase(self) -> float:
        return max(0.0, self.current.duplication.duplication_density - self.baseline.duplication.duplication_density)

    @property
    def new_clone_groups(self) -> int:
        return sum((_clone_groups(self.current) - _clone_groups(self.baseline)).values())

    @property
    def new_cycle_groups(self) -> int:
        before = {frozenset(cycle.modules) for cycle in self.baseline.imports.cycles}
        after = {frozenset(cycle.modules) for cycle in self.current.imports.cycles}
        return len(after - before)

    @property
    def new_architecture_violations(self) -> int:
        return sum((_architecture_violations(self.current) - _architecture_violations(self.baseline)).values())

    @property
    def resolved_architecture_violations(self) -> int:
        return sum((_architecture_violations(self.baseline) - _architecture_violations(self.current)).values())
