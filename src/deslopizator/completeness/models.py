from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deslopizator.inventory.models import ProjectInventory
    from deslopizator.models import ComplexityMetrics
    from deslopizator.duplication.models import DuplicationMetrics
    from deslopizator.imports.models import ImportMetrics
    from deslopizator.scoring.models import SlopScore


class AnalysisStatus(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    NOT_APPLICABLE = "not-applicable"


@dataclass(frozen=True)
class DimensionCompleteness:
    status: AnalysisStatus
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class AuditCompleteness:
    complexity: DimensionCompleteness
    duplication: DimensionCompleteness
    imports: DimensionCompleteness


@dataclass(frozen=True)
class AuditResult:
    inventory: "ProjectInventory"
    complexity: "ComplexityMetrics"
    duplication: "DuplicationMetrics"
    imports: "ImportMetrics"
    completeness: AuditCompleteness
    score: "SlopScore"
