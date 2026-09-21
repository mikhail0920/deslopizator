import fnmatch
import tomllib
from pathlib import Path, PurePosixPath

from deslopizator.inventory.models import FileKind, ProjectConfig, ProjectInventory, SourceFile


def _as_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def load_config(root: Path) -> ProjectConfig:
    config_path = root / "pyproject.toml"
    if not config_path.is_file():
        return ProjectConfig()
    with config_path.open("rb") as stream:
        document = tomllib.load(stream)
    deslop = document.get("tool", {}).get("deslop", {})
    if not isinstance(deslop, dict):
        return ProjectConfig()
    classification = deslop.get("classification", {})
    if not isinstance(classification, dict):
        classification = {}
    source_roots = _as_strings(deslop.get("source-roots")) or ("src",)
    return ProjectConfig(
        source_roots=source_roots,
        exclude=_as_strings(deslop.get("exclude")),
        generated=_as_strings(classification.get("generated")),
    )


def _relative_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _matches(path: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/").lstrip("./")
    return fnmatch.fnmatchcase(path, normalized) or PurePosixPath(path).match(normalized)


def _kind(relative_path: str, config: ProjectConfig) -> FileKind:
    if any(_matches(relative_path, pattern) for pattern in config.exclude):
        return FileKind.EXCLUDED
    if any(_matches(relative_path, pattern) for pattern in config.generated):
        return FileKind.GENERATED
    path = PurePosixPath(relative_path)
    if "tests" in path.parts or "test" in path.parts or path.name.startswith("test_") or path.name.endswith("_test.py"):
        return FileKind.TEST
    return FileKind.PRODUCTION


def classify_path(relative_path: str, config: ProjectConfig) -> FileKind:
    return _kind(relative_path.replace("\\", "/"), config)


def _module_for_path(path: Path, root: Path, source_roots: tuple[Path, ...]) -> str | None:
    for source_root in source_roots:
        if path.resolve().is_relative_to(source_root.resolve()):
            relative = path.resolve().relative_to(source_root.resolve())
            parts = list(relative.with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            return ".".join(parts) or None
    return None


def discover_project(path: Path | str) -> ProjectInventory:
    requested = Path(path).resolve()
    root = requested.parent if requested.is_file() else requested
    config = load_config(root)
    configured_roots = tuple((root / source_root).resolve() for source_root in config.source_roots)
    existing_roots = tuple(source_root for source_root in configured_roots if source_root.is_dir())
    source_roots = existing_roots or (root,)
    if requested.is_file():
        paths = [requested] if requested.suffix == ".py" else []
    else:
        ignored = {".git", ".venv", "venv", "__pycache__"}
        paths = sorted(
            file
            for file in root.rglob("*.py")
            if not any(part in ignored for part in file.parts)
        )
    files = tuple(
        SourceFile(
            path=str(file),
            module=_module_for_path(file, root, source_roots),
            kind=_kind(_relative_posix(file, root), config),
        )
        for file in paths
    )
    return ProjectInventory(str(root), files, tuple(str(source_root) for source_root in source_roots))
