"""Run the advisory detector corpus over a directory of local repositories.

Usage:
    python tools/run_corpus.py /path/to/repos

The command intentionally does not clone repositories. Each immediate child
directory is treated as one project; a path containing a single repository is
also accepted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_package() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "src"
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))


def _projects(root: Path) -> list[Path]:
    if (root / ".git").exists() or (root / "pyproject.toml").exists():
        return [root]
    return sorted((path for path in root.iterdir() if path.is_dir() and path.name != ".git"), key=lambda path: path.name.lower())


def _kloc(result) -> int:
    lines = 0
    for source_file in result.inventory.production_files:
        try:
            lines += len(Path(source_file.path).read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeError):
            continue
    return round(lines / 1000)


def _result(path: Path) -> dict[str, object]:
    from deslopizator.audit import analyze_project

    result = analyze_project(path)
    counts = {"DS101": 0, "DS102": 0, "DS103": 0, "DS104": 0, "DS105": 0}
    codes = {
        "pass-through": "DS101",
        "delegating-class": "DS102",
        "delegation-chain": "DS103",
        "single-implementation-abstraction": "DS104",
        "swallowed-exception": "DS105",
    }
    for finding in result.smells.findings if result.smells else ():
        counts[codes.get(finding.rule, finding.rule)] = counts.get(codes.get(finding.rule, finding.rule), 0) + 1
    return {
        "project": str(path),
        "kloc": _kloc(result),
        "score": result.score.total,
        "smells": {key: value for key, value in counts.items() if value},
    }


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    if len(arguments) != 1:
        print("usage: python tools/run_corpus.py /path/to/repos", file=sys.stderr)
        return 2
    _load_package()
    root = Path(arguments[0]).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    rows = []
    for path in _projects(root):
        try:
            rows.append(_result(path))
        except Exception as error:  # keep one broken legacy project from hiding the rest
            rows.append({"project": str(path), "kloc": None, "score": None, "smells": {}, "error": str(error)})
    print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
