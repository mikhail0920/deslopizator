from dataclasses import dataclass
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
        return max(0, self.current.complexity.eroded_function_count - self.baseline.complexity.eroded_function_count)

    @property
    def density_increase(self) -> float:
        return max(0.0, self.current.duplication.duplication_density - self.baseline.duplication.duplication_density)

    @property
    def new_clone_groups(self) -> int:
        return max(0, self.current.duplication.clone_group_count - self.baseline.duplication.clone_group_count)

    @property
    def new_cycle_groups(self) -> int:
        return max(0, self.current.imports.cycle_group_count - self.baseline.imports.cycle_group_count)
