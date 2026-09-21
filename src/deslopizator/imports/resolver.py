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


def resolve_imports(
    source: str,
    parsed: ParsedImport,
    internal: set[str],
    packages: set[str],
) -> tuple[ImportEdge | UnresolvedImport, ...]:
    """Resolve every imported module; imported attributes belong to their base module."""
    if parsed.level:
        package = source.split(".") if source in packages else source.split(".")[:-1]
        base_length = len(package) - parsed.level + 1
        if base_length < 0:
            return (UnresolvedImport(source, parsed.raw_import, parsed.line),)
        prefix = package[:base_length]
        base = ".".join([*prefix, parsed.module] if parsed.module else prefix)
    else:
        base = parsed.module or parsed.raw_import
        if base.split(".")[0] not in {name.split(".")[0] for name in internal}:
            return ()

    targets: set[str] = set()
    unresolved: list[UnresolvedImport] = []
    for name in parsed.names or ("",):
        child = f"{base}.{name}" if base else name
        if name and child in internal:
            targets.add(child)
        elif base in internal:
            targets.add(base)
        else:
            unresolved.append(UnresolvedImport(source, parsed.raw_import, parsed.line))
    return tuple(ImportEdge(source, target, parsed.line, parsed.kind) for target in sorted(targets)) + tuple(dict.fromkeys(unresolved))


def resolve_import(source: str, parsed: ParsedImport, internal: set[str]):
    """Compatibility helper for callers expecting one resolved import."""
    packages = {name for name in internal if any(other.startswith(name + ".") for other in internal)}
    resolved = resolve_imports(source, parsed, internal, packages)
    return resolved[0] if resolved else None
