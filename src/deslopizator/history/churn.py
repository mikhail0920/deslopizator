from pathlib import Path

from deslopizator.history.git import GitUnavailable, collect_file_churn
from deslopizator.history.models import FileChurn


def _zero_churn(paths: list[Path]) -> tuple[FileChurn, ...]:
    return tuple(FileChurn(str(path), 0, 0, 0, 0, 0, 0) for path in sorted(paths, key=str))


def analyze_churn(inventory) -> tuple[tuple[FileChurn, ...], bool, tuple[str, ...]]:
    """Return file churn, availability, and non-fatal Git diagnostics."""
    paths = [Path(file.path) for file in inventory.production_files]
    try:
        return collect_file_churn(Path(inventory.root), paths), True, ()
    except (GitUnavailable, ValueError, OSError):
        # Keep diagnostics portable: subprocess errors can contain absolute
        # checkout paths and would make otherwise identical snapshots differ.
        return _zero_churn(paths), False, ("Git history unavailable",)
