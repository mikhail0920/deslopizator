from collections import defaultdict
from pathlib import Path

from deslopizator.imports.models import ImportAnalysis, ImportCycle, ImportEdge, ImportMetrics, UnresolvedImport
from deslopizator.imports.parser import parse_file
from deslopizator.imports.resolver import module_name_for_path, resolve_imports


def build_graph(edges: tuple[ImportEdge, ...] | list[ImportEdge]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.kind == "runtime":
            graph[edge.source].add(edge.target)
            graph.setdefault(edge.target, set())
    return dict(graph)


def find_cycles(graph: dict[str, set[str]]) -> tuple[ImportCycle, ...]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(graph.get(node, ())):
            if target not in indices:
                strongconnect(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while True:
            target = stack.pop()
            on_stack.remove(target)
            component.append(target)
            if target == node:
                break
        component.sort()
        if len(component) > 1 or node in graph.get(node, set()):
            components.append(tuple(component))

    for node in sorted(graph):
        if node not in indices:
            strongconnect(node)
    return tuple(ImportCycle(modules) for modules in sorted(components))


def _analysis_paths(paths_or_inventory) -> list[Path]:
    if hasattr(paths_or_inventory, "production_files"):
        return [Path(file.path) for file in paths_or_inventory.production_files]
    return [Path(path) for path in paths_or_inventory]


def analyze_imports(paths: list[Path | str], source_root: Path | str | None = None) -> ImportAnalysis:
    normalized_paths = sorted(_analysis_paths(paths), key=str)
    if source_root is None and hasattr(paths, "source_roots"):
        modules = {Path(file.path): file.module for file in paths.production_files}
    else:
        if source_root is None:
            raise ValueError("source_root is required when analyzing a path list")
        root = Path(source_root).resolve()
        modules = {
            path: module_name_for_path(path, root)
            for path in normalized_paths if path.resolve().is_relative_to(root)
        }
    internal = {module for module in modules.values() if module}
    packages = {module for path, module in modules.items() if path.name == "__init__.py" and module}
    edges: list[ImportEdge] = []
    unresolved: list[UnresolvedImport] = []
    errors: list[str] = []
    for path in normalized_paths:
        source = modules.get(path)
        if not source:
            errors.append(f"{path}: no module name in configured source roots")
            continue
        try:
            parsed_imports = parse_file(path)
        except (OSError, SyntaxError, UnicodeError) as error:
            errors.append(f"{path}: {error}")
            continue
        for parsed in parsed_imports:
            for resolved in resolve_imports(source, parsed, internal, packages):
                if isinstance(resolved, ImportEdge):
                    edges.append(resolved)
                else:
                    unresolved.append(resolved)
    edge_tuple = tuple(sorted(edges, key=lambda edge: (edge.source, edge.target, edge.line, edge.kind)))
    unresolved_tuple = tuple(sorted(unresolved, key=lambda item: (item.source, item.line, item.raw_import)))
    cycles = find_cycles(build_graph(edge_tuple))
    internal_count = len(internal)
    modules_in_cycles = len({module for cycle in cycles for module in cycle.modules})
    metrics = ImportMetrics(
        internal_module_count=internal_count,
        runtime_edge_count=sum(edge.kind == "runtime" for edge in edge_tuple),
        type_checking_edge_count=sum(edge.kind == "type_checking" for edge in edge_tuple),
        cycle_group_count=len(cycles),
        modules_in_cycles=modules_in_cycles,
        cycle_density=modules_in_cycles / internal_count if internal_count else 0.0,
        unresolved_import_count=len(unresolved_tuple),
        cycles=cycles,
    )
    return ImportAnalysis(edge_tuple, unresolved_tuple, cycles, metrics, tuple(errors))
