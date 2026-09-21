from pathlib import Path

from deslopizator.complexity import analyze_complexity
from deslopizator.completeness.models import AnalysisStatus, AuditCompleteness, AuditResult, DimensionCompleteness
from deslopizator.duplication.detector import analyze_duplication_facts
from deslopizator.imports.graph import analyze_imports
from deslopizator.inventory.classifier import discover_project
from deslopizator.scoring.scorer import score


def _status_for_production(errors: tuple[str, ...], production_count: int) -> DimensionCompleteness:
    if production_count == 0:
        return DimensionCompleteness(AnalysisStatus.NOT_APPLICABLE, ())
    if errors:
        return DimensionCompleteness(AnalysisStatus.PARTIAL, errors)
    return DimensionCompleteness(AnalysisStatus.COMPLETE, ())


def analyze_project(path: Path | str) -> AuditResult:
    inventory = discover_project(path)
    production_paths = [Path(file.path) for file in inventory.production_files]
    complexity, complexity_errors = analyze_complexity(production_paths)
    clone_groups, duplication, duplication_errors = analyze_duplication_facts(inventory)
    imports = analyze_imports(inventory)

    import_reasons = tuple(
        f"unresolved local import: {item.source} -> {item.raw_import}"
        for item in imports.unresolved
    ) + imports.errors
    completeness = AuditCompleteness(
        complexity=_status_for_production(complexity_errors, len(production_paths)),
        duplication=_status_for_production(duplication_errors, len(production_paths)),
        imports=(
            DimensionCompleteness(AnalysisStatus.NOT_APPLICABLE, ())
            if not production_paths
            else DimensionCompleteness(
                AnalysisStatus.PARTIAL if import_reasons else AnalysisStatus.COMPLETE,
                import_reasons,
            )
        ),
    )
    import_metrics = imports.metrics
    return AuditResult(
        inventory,
        complexity,
        duplication,
        import_metrics,
        completeness,
        score(complexity, duplication, import_metrics, completeness),
        clone_groups,
    )
