from collections import defaultdict
from pathlib import Path

from deslopizator.imports.models import ImportAnalysis, ImportCycle, ImportEdge, ImportMetrics, UnresolvedImport
from deslopizator.imports.parser import parse_file
from deslopizator.imports.resolver import internal_module_names, module_name_for_path, resolve_import


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


def analyze_imports(paths: list[Path | str], source_root: Path | str) -> ImportAnalysis:
    normalized_paths = sorted((Path(path) for path in paths), key=str)
    root = Path(source_root)
    internal = internal_module_names(normalized_paths, root)
    edges: list[ImportEdge] = []
    unresolved: list[UnresolvedImport] = []
    for path in normalized_paths:
        if not path.resolve().is_relative_to(root.resolve()):
            continue
        source = module_name_for_path(path, root)
        for parsed in parse_file(path):
            resolved = resolve_import(source, parsed, internal)
            if isinstance(resolved, ImportEdge):
                edges.append(resolved)
            elif isinstance(resolved, UnresolvedImport):
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
    )
    return ImportAnalysis(edge_tuple, unresolved_tuple, cycles, metrics)
