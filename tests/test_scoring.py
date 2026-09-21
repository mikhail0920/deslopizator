import pytest

from deslopizator.completeness import AnalysisStatus, AuditCompleteness, DimensionCompleteness
from deslopizator.duplication.models import DuplicationMetrics
from deslopizator.imports.models import ImportMetrics
from deslopizator.models import ComplexityMetrics
from deslopizator.scoring import ScoringParameters, count_burden, density_burden, score
from deslopizator.scoring.formulas import dimension_score


def complete():
    dimension = DimensionCompleteness(AnalysisStatus.COMPLETE, ())
    return AuditCompleteness(dimension, dimension, dimension)


def metrics(complexity_density=0.0, complexity_count=0, duplication_density=0.0, clone_count=0, cycle_density=0.0, cycle_count=0):
    complexity = ComplexityMetrics((), 0, 1.0, complexity_density, complexity_count)
    duplication = DuplicationMetrics(clone_count, 0, 0, 0, duplication_density)
    imports = ImportMetrics(0, 0, 0, cycle_count, 0, cycle_density, 0)
    return complexity, duplication, imports


def test_ideal_project_has_zero_score():
    values = metrics()

    result = score(*values, complete())

    assert result.total == 0.0
    assert result.partial is False
    assert result.complexity.score == 0.0


@pytest.mark.parametrize(
    ("dimension", "low", "high"),
    [
        ("complexity_density", 0.05, 0.20),
        ("complexity_count", 1, 5),
        ("duplication_density", 0.01, 0.10),
        ("clone_count", 1, 5),
        ("cycle_density", 0.01, 0.08),
        ("cycle_count", 1, 3),
    ],
)
def test_each_raw_metric_is_monotonic(dimension, low, high):
    low_values = {"complexity_density": 0.0, "complexity_count": 0, "duplication_density": 0.0, "clone_count": 0, "cycle_density": 0.0, "cycle_count": 0}
    high_values = dict(low_values)
    low_values[dimension] = low
    high_values[dimension] = high

    low_score = score(*metrics(**low_values), complete()).total
    high_score = score(*metrics(**high_values), complete()).total

    assert high_score >= low_score


def test_density_saturates_and_count_burden_stays_below_one():
    assert density_burden(10.0, 0.25) == 1.0
    assert count_burden(0, 20) == 0.0
    assert count_burden(10_000, 20) < 1.0


def test_dimension_score_uses_both_density_and_count():
    result = dimension_score(0.25, 20, ScoringParameters().complexity)

    assert result.density_burden == 1.0
    assert 0.0 < result.count_burden < 1.0
    assert result.score == pytest.approx(0.5 * (1.0 + result.count_burden))


def test_golden_score_uses_unrounded_intermediate_values():
    values = metrics(
        complexity_density=0.25,
        complexity_count=2,
        duplication_density=0.075,
        clone_count=1,
        cycle_density=0.05,
        cycle_count=1,
    )

    result = score(*values, complete())

    assert result.total == pytest.approx(42.12686662913801)


def test_adding_clean_functions_does_not_reduce_absolute_count_burden():
    one_eroded = metrics(complexity_density=0.5, complexity_count=1)
    two_eroded = metrics(complexity_density=0.5, complexity_count=2)

    first = score(*one_eroded, complete()).complexity
    second = score(*two_eroded, complete()).complexity

    assert second.count_burden > first.count_burden


def test_partial_score_is_numeric_but_marked_partial():
    partial = AuditCompleteness(
        DimensionCompleteness(AnalysisStatus.PARTIAL, ("syntax error",)),
        DimensionCompleteness(AnalysisStatus.COMPLETE, ()),
        DimensionCompleteness(AnalysisStatus.COMPLETE, ()),
    )

    result = score(*metrics(complexity_density=0.1, complexity_count=1), partial)

    assert result.total is not None
    assert result.partial is True


def test_not_applicable_dimensions_are_not_replaced_with_zero():
    not_applicable = DimensionCompleteness(AnalysisStatus.NOT_APPLICABLE, ())
    completeness = AuditCompleteness(not_applicable, not_applicable, not_applicable)

    result = score(*metrics(), completeness)

    assert result.total is None
    assert result.complexity is None
    assert result.duplication is None
    assert result.cycles is None
