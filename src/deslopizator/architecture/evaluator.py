from __future__ import annotations

from fnmatch import fnmatchcase

from deslopizator.architecture.models import (
    ArchitectureConfig,
    ArchitectureIndependent,
    ArchitectureMetrics,
    ArchitectureViolation,
)
from deslopizator.architecture.parser import ArchitectureConfigError


def _matches(module: str, pattern: str) -> bool:
    if pattern.endswith(".**"):
        prefix = pattern[:-3].rstrip(".")
        return module == prefix or module.startswith(prefix + ".")
    return fnmatchcase(module, pattern)


def _layer_assignments(inventory, config: ArchitectureConfig) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for source_file in inventory.production_files:
        if not source_file.module:
            continue
        matches = [layer.name for layer in config.layers if any(_matches(source_file.module, pattern) for pattern in layer.patterns)]
        if len(matches) > 1:
            raise ArchitectureConfigError(
                f"production module {source_file.module} matches multiple architecture layers: {', '.join(matches)}"
            )
        if matches:
            assignments[source_file.module] = matches[0]
    return assignments


def _independent_match(source: str, target: str, rule: ArchitectureIndependent) -> bool:
    source_matches = [index for index, pattern in enumerate(rule.patterns) if _matches(source, pattern)]
    target_matches = [index for index, pattern in enumerate(rule.patterns) if _matches(target, pattern)]
    return any(left != right for left in source_matches for right in target_matches)


def evaluate_architecture(inventory, edges, config: ArchitectureConfig) -> ArchitectureMetrics:
    """Evaluate explicit contracts against already-resolved import edges."""
    assignments = _layer_assignments(inventory, config)
    violations: list[ArchitectureViolation] = []
    for edge in edges:
        if edge.kind != "runtime":
            continue
        source_layer = assignments.get(edge.source)
        target_layer = assignments.get(edge.target)
        if source_layer is not None and target_layer is not None:
            for rule in config.forbidden:
                if source_layer == rule.source_layer and target_layer == rule.target_layer:
                    violations.append(ArchitectureViolation(
                        edge.source, edge.target, source_layer, target_layer, edge.line,
                        f"forbidden: {rule.source_layer} -> {rule.target_layer}",
                    ))
            for rule in config.layered:
                positions = {name: index for index, name in enumerate(rule.layers)}
                if source_layer in positions and target_layer in positions and positions[source_layer] > positions[target_layer]:
                    violations.append(ArchitectureViolation(
                        edge.source, edge.target, source_layer, target_layer, edge.line,
                        "layered: " + " -> ".join(rule.layers),
                    ))
        for rule in config.independent:
            if _independent_match(edge.source, edge.target, rule):
                violations.append(ArchitectureViolation(
                    edge.source, edge.target, source_layer or "", target_layer or "", edge.line,
                    "independent: " + ", ".join(rule.patterns),
                ))
    ordered = tuple(sorted(
        violations,
        key=lambda item: (item.source_module, item.target_module, item.rule, item.line),
    ))
    return ArchitectureMetrics(len(ordered), ordered)
