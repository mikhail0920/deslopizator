from deslopizator.completeness.models import AnalysisStatus, AuditCompleteness
from deslopizator.models import ComplexityMetrics
from deslopizator.duplication.models import DuplicationMetrics
from deslopizator.imports.models import ImportMetrics
from deslopizator.scoring.formulas import dimension_score
from deslopizator.scoring.models import ScoringParameters, SlopScore
from deslopizator.scoring.version import SCORING_VERSION


def _dimension_or_none(raw_density: float, raw_count: int, status: AnalysisStatus, parameters):
    if status is AnalysisStatus.NOT_APPLICABLE:
        return None
    return dimension_score(raw_density, raw_count, parameters)


def score(
    complexity: ComplexityMetrics,
    duplication: DuplicationMetrics,
    cycles: ImportMetrics,
    completeness: AuditCompleteness,
    parameters: ScoringParameters = ScoringParameters(),
) -> SlopScore:
    complexity_score = _dimension_or_none(
        complexity.eroded_function_mass / complexity.total_function_mass if complexity.total_function_mass else 0.0,
        complexity.eroded_function_count,
        completeness.complexity.status,
        parameters.complexity,
    )
    duplication_score = _dimension_or_none(
        duplication.duplication_density,
        duplication.clone_group_count,
        completeness.duplication.status,
        parameters.duplication,
    )
    cycle_score = _dimension_or_none(
        cycles.cycle_density,
        cycles.cycle_group_count,
        completeness.imports.status,
        parameters.cycles,
    )
    dimensions = (complexity_score, duplication_score, cycle_score)
    partial = any(
        status.status is AnalysisStatus.PARTIAL
        for status in (completeness.complexity, completeness.duplication, completeness.imports)
    )
    if any(dimension is None for dimension in dimensions):
        total = None
    else:
        total = 100.0 * (
            parameters.complexity_weight * complexity_score.score
            + parameters.duplication_weight * duplication_score.score
            + parameters.cycles_weight * cycle_score.score
        )
    return SlopScore(SCORING_VERSION, total, complexity_score, duplication_score, cycle_score, partial)


def score_audit(audit_result, parameters: ScoringParameters = ScoringParameters()) -> SlopScore:
    return score(audit_result.complexity, audit_result.duplication, audit_result.imports, audit_result.completeness, parameters)
