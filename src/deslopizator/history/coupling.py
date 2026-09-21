"""Change coupling derived from Git commit file sets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
import re
import subprocess

from deslopizator.history.git import GitUnavailable
from deslopizator.history.models import ChangeCoupling


@dataclass(frozen=True)
class _CommitFiles:
    timestamp: int
    paths: frozenset[str]


_COMMIT = re.compile(r"^[0-9a-f]{7,40}\t(\d+)$")
_NUMSTAT = re.compile(r"^(\d+|-)\t(\d+|-)\t(.+)$")


def _parse_commit_file_sets(output: str) -> tuple[_CommitFiles, ...]:
    commits: list[_CommitFiles] = []
    timestamp: int | None = None
    paths: set[str] = set()

    def flush() -> None:
        if timestamp is not None:
            commits.append(_CommitFiles(timestamp, frozenset(paths)))

    for line in output.splitlines():
        match = _COMMIT.match(line)
        if match:
            flush()
            timestamp = int(match.group(1))
            paths = set()
            continue
        if timestamp is None:
            continue
        match = _NUMSTAT.match(line)
        if match:
            paths.add(match.group(3).replace("\\", "/").lstrip("./"))
    flush()
    return tuple(commits)


def _read_commit_file_sets(root: Path) -> tuple[_CommitFiles, ...]:
    command = [
        "git",
        "-C",
        str(root),
        "log",
        "--no-renames",
        "--format=%H%x09%ct",
        "--since=180 days ago",
        "--numstat",
        "--",
        ".",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise GitUnavailable(str(error)) from error
    return _parse_commit_file_sets(completed.stdout)


def _production_paths(inventory) -> dict[str, str]:
    root = Path(inventory.root).resolve()
    return {
        Path(source_file.path).resolve().relative_to(root).as_posix(): source_file.path
        for source_file in inventory.production_files
    }


def static_dependency_pairs(inventory, edges) -> frozenset[frozenset[str]]:
    """Return production-file pairs connected by an import edge either way."""
    by_module = {source_file.module: source_file.path for source_file in inventory.production_files if source_file.module}
    pairs: set[frozenset[str]] = set()
    for edge in edges:
        source = by_module.get(edge.source)
        target = by_module.get(edge.target)
        if source is None or target is None or source == target:
            continue
        pairs.add(frozenset((source, target)))
    return frozenset(pairs)


def build_couplings(
    commit_files,
    *,
    static_dependencies: frozenset[frozenset[str]] | set[frozenset[str]] = frozenset(),
) -> tuple[ChangeCoupling, ...]:
    """Build qualifying, uniquely ordered coupling findings from commit file sets."""
    commits = [frozenset(paths) for paths in commit_files]
    dependencies = {frozenset(pair) for pair in static_dependencies}
    changes: dict[str, int] = {}
    cochanges: dict[tuple[str, str], int] = {}
    for files in commits:
        for path in files:
            changes[path] = changes.get(path, 0) + 1
        for file_a, file_b in combinations(sorted(files), 2):
            key = (file_a, file_b)
            cochanges[key] = cochanges.get(key, 0) + 1

    findings: list[ChangeCoupling] = []
    for (file_a, file_b), together in cochanges.items():
        changes_a = changes[file_a]
        changes_b = changes[file_b]
        probability_b_given_a = together / changes_a
        probability_a_given_b = together / changes_b
        strength = min(probability_b_given_a, probability_a_given_b)
        if together < 5 or strength < 0.70:
            continue
        findings.append(
            ChangeCoupling(
                file_a=file_a,
                file_b=file_b,
                changes_a=changes_a,
                changes_b=changes_b,
                cochanges=together,
                probability_b_given_a=probability_b_given_a,
                probability_a_given_b=probability_a_given_b,
                strength=strength,
                has_static_dependency=frozenset((file_a, file_b)) in dependencies,
            )
        )
    return tuple(sorted(findings, key=lambda item: (-item.strength, -item.cochanges, item.file_a, item.file_b)))


def analyze_coupling(inventory, imports, *, now: datetime | None = None) -> tuple[tuple[ChangeCoupling, ...], bool, tuple[str, ...]]:
    """Analyze the last 180 days; Git absence is a non-fatal unavailable state."""
    root = Path(inventory.root).resolve()
    paths = _production_paths(inventory)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    cutoff = reference.timestamp() - 180 * 86400
    try:
        commits = _read_commit_file_sets(root)
    except (GitUnavailable, ValueError, OSError):
        return (), False, ("Change coupling unavailable",)

    production_commits = []
    for commit in commits:
        if commit.timestamp < cutoff:
            continue
        production_commits.append({paths[path] for path in commit.paths if path in paths})
    dependencies = static_dependency_pairs(inventory, imports.edges if hasattr(imports, "edges") else imports)
    return build_couplings(production_commits, static_dependencies=dependencies), True, ()


analyze_change_coupling = analyze_coupling
calculate_change_coupling = build_couplings
