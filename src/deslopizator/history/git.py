"""Small, read-only adapters around ``git log --numstat``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess

from deslopizator.history.models import FileChurn


class GitUnavailable(RuntimeError):
    """Raised when the project has no usable Git history."""


@dataclass(frozen=True)
class _Commit:
    timestamp: int
    author: str
    added: int = 0
    deleted: int = 0


_COMMIT = re.compile(r"^[0-9a-f]{7,40}\t([^\t]*)\t(\d+)$")
_NUMSTAT = re.compile(r"^(\d+|-)\t(\d+|-)\t(.+)$")


def _parse_log_lines(output: str) -> tuple[_Commit, ...]:
    commits: list[_Commit] = []
    current_timestamp: int | None = None
    current_author: str | None = None
    added = deleted = 0

    def flush() -> None:
        if current_timestamp is not None and current_author is not None:
            commits.append(_Commit(current_timestamp, current_author, added, deleted))

    for line in output.splitlines():
        match = _COMMIT.match(line)
        if match:
            flush()
            current_timestamp = int(match.group(2))
            current_author = match.group(1)
            added = deleted = 0
            continue
        if current_timestamp is None:
            continue
        match = _NUMSTAT.match(line)
        if match:
            added += 0 if match.group(1) == "-" else int(match.group(1))
            deleted += 0 if match.group(2) == "-" else int(match.group(2))
    flush()
    return tuple(commits)


def _read_log(root: Path, path: Path) -> tuple[_Commit, ...]:
    relative_path = path.resolve().relative_to(root.resolve()).as_posix()
    command = [
        "git",
        "-C",
        str(root),
        "log",
        "--follow",
        "--no-renames",
        "--format=%H%x09%ae%x09%ct",
        "--since=365 days ago",
        "--numstat",
        "--",
        relative_path,
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
    return _parse_log_lines(completed.stdout)


def collect_file_churn(
    root: Path | str,
    paths: list[Path | str] | tuple[Path | str, ...],
    *,
    now: datetime | None = None,
) -> tuple[FileChurn, ...]:
    """Collect deterministic per-file churn using only Git log numstats."""
    project_root = Path(root).resolve()
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    now_timestamp = reference.timestamp()
    windows = (90 * 86400, 180 * 86400, 365 * 86400)
    result: list[FileChurn] = []
    for raw_path in sorted((Path(path).resolve() for path in paths), key=lambda item: item.as_posix()):
        commits = _read_log(project_root, raw_path)
        in_window = {
            days: tuple(commit for commit in commits if commit.timestamp >= now_timestamp - seconds)
            for days, seconds in zip((90, 180, 365), windows)
        }
        recent = in_window[180]
        result.append(
            FileChurn(
                path=str(raw_path),
                commits_90d=len(in_window[90]),
                commits_180d=len(recent),
                commits_365d=len(in_window[365]),
                authors_180d=len({commit.author for commit in recent}),
                added_lines_180d=sum(commit.added for commit in recent),
                deleted_lines_180d=sum(commit.deleted for commit in recent),
            )
        )
    return tuple(result)
