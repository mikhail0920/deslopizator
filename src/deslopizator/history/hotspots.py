from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from deslopizator.duplication.tokenizer import production_code_lines
from deslopizator.history.models import FileChurn, FileStructuralDebt, Hotspot


def _normalize(value: float, maximum: float) -> float:
    return value / maximum if maximum else 0.0


def _file_duplication(groups) -> tuple[dict[str, int], dict[str, int]]:
    lines: dict[str, set[int]] = defaultdict(set)
    instances: dict[str, int] = defaultdict(int)
    for group in groups:
        for instance in group.instances:
            instances[instance.path] += 1
            lines[instance.path].update(range(instance.start_line, instance.end_line + 1))
    duplicated_lines: dict[str, int] = {}
    for path, duplicated in lines.items():
        try:
            duplicated_lines[path] = len(duplicated & production_code_lines(Path(path).read_text(encoding="utf-8")))
        except (OSError, SyntaxError, UnicodeError):
            duplicated_lines[path] = len(duplicated)
    return duplicated_lines, dict(instances)


def build_structural_debt(inventory, complexity, clone_groups, imports) -> tuple[FileStructuralDebt, ...]:
    """Aggregate existing complexity, duplication, and runtime-cycle facts per file."""
    complexity_by_path = {item.path: item for item in complexity.files}
    duplicated_lines, clone_instances = _file_duplication(clone_groups)
    cyclic_modules = {module for cycle in imports.cycles for module in cycle.modules}
    files = sorted(inventory.production_files, key=lambda item: item.path)

    raw: list[tuple[str, float, int, int, int, bool]] = []
    for source_file in files:
        path = source_file.path
        file_complexity = complexity_by_path.get(path)
        eroded_mass = file_complexity.eroded_mass if file_complexity else 0.0
        eroded_count = file_complexity.eroded_function_count if file_complexity else 0
        duplicate_lines = duplicated_lines.get(path, 0)
        duplicate_instances = clone_instances.get(path, 0)
        participates = bool(source_file.module and source_file.module in cyclic_modules)
        raw.append((path, eroded_mass, eroded_count, duplicate_lines, duplicate_instances, participates))

    max_mass = max((item[1] for item in raw), default=0.0)
    max_eroded_count = max((item[2] for item in raw), default=0)
    max_duplicate_lines = max((item[3] for item in raw), default=0)
    max_clone_instances = max((item[4] for item in raw), default=0)
    result = []
    for path, mass, count, duplicate_lines, duplicate_instances, participates in raw:
        complexity_debt = 0.7 * _normalize(mass, max_mass) + 0.3 * _normalize(count, max_eroded_count)
        duplication_debt = 0.7 * _normalize(duplicate_lines, max_duplicate_lines) + 0.3 * _normalize(duplicate_instances, max_clone_instances)
        cycle_debt = 1.0 if participates else 0.0
        structural_debt = 0.5 * complexity_debt + 0.3 * duplication_debt + 0.2 * cycle_debt
        result.append(
            FileStructuralDebt(
                path, mass, count, duplicate_lines, duplicate_instances, participates, structural_debt
            )
        )
    return tuple(result)


def priority(structural_debt: float, churn: int, max_structural_debt: float, max_churn: int) -> float:
    if structural_debt <= 0 or churn <= 0:
        return 0.0
    return _normalize(structural_debt, max_structural_debt) * _normalize(churn, max_churn)


def build_hotspots(
    structural_debt: tuple[FileStructuralDebt, ...],
    churn: tuple[FileChurn, ...],
) -> tuple[Hotspot, ...]:
    churn_by_path = {item.path: item for item in churn}
    zero = lambda path: FileChurn(path, 0, 0, 0, 0, 0, 0)
    max_debt = max((item.structural_debt for item in structural_debt), default=0.0)
    max_churn = max((churn_by_path.get(item.path, zero(item.path)).commits_180d for item in structural_debt), default=0)
    result = [
        Hotspot(
            item.path,
            item.structural_debt,
            churn_by_path.get(item.path, zero(item.path)).commits_180d,
            priority(
                item.structural_debt,
                churn_by_path.get(item.path, zero(item.path)).commits_180d,
                max_debt,
                max_churn,
            ),
        )
        for item in structural_debt
    ]
    return tuple(sorted(result, key=lambda item: (-item.priority, -item.structural_debt, -item.churn, item.path)))
