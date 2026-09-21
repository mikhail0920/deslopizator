from pathlib import Path

from deslopizator.imports.models import ImportEdge, UnresolvedImport
from deslopizator.imports.parser import ParsedImport


def module_name_for_path(path: Path, source_root: Path) -> str:
    relative = path.resolve().relative_to(source_root.resolve())
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def internal_module_names(paths: list[Path], source_root: Path) -> set[str]:
    return {module_name_for_path(path, source_root) for path in paths if path.resolve().is_relative_to(source_root.resolve())}


def _absolute_candidate(parsed: ParsedImport, internal: set[str]) -> str | None:
    if parsed.module is None:
        return None
    for name in parsed.names:
        candidate = f"{parsed.module}.{name}"
        if candidate in internal:
            return candidate
    if parsed.module in internal:
        return parsed.module
    return None


def _relative_candidates(source: str, parsed: ParsedImport, internal: set[str]) -> list[str]:
    is_package_module = any(name.startswith(f"{source}.") for name in internal)
    package = source.split(".") if is_package_module else source.split(".")[:-1]
    base_length = len(package) - (parsed.level - 1)
    if base_length < 0:
        return []
    prefix = package[:base_length]
    candidates: list[str] = []
    if parsed.module:
        candidates.append(".".join([*prefix, parsed.module]))
    else:
        candidates.extend(".".join([*prefix, name]) for name in parsed.names if name != "*")
    return [candidate for candidate in candidates if candidate]


def resolve_import(source: str, parsed: ParsedImport, internal: set[str]) -> ImportEdge | UnresolvedImport | None:
    if parsed.level:
        candidates = _relative_candidates(source, parsed, internal)
        for candidate in candidates:
            if candidate in internal:
                return ImportEdge(source, candidate, parsed.line, parsed.kind)
        return UnresolvedImport(source, parsed.raw_import, parsed.line)

    top_level = (parsed.module or parsed.raw_import).split(".")[0]
    internal_roots = {name.split(".")[0] for name in internal}
    if top_level not in internal_roots:
        return None
    candidate = _absolute_candidate(parsed, internal)
    if candidate is not None:
        return ImportEdge(source, candidate, parsed.line, parsed.kind)
    return UnresolvedImport(source, parsed.raw_import, parsed.line)
