"""Measure audit phases on generated synthetic repositories.

Usage:
    python tools/benchmark.py
    python tools/benchmark.py --sizes 1000 10000
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path


def _load_package() -> None:
    source = Path(__file__).resolve().parents[1] / "src"
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))


def _generate(root: Path, count: int) -> None:
    source = "def value(number):\n    return number + 1\n"
    for index in range(count):
        path = root / "src" / f"module_{index:05d}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")


def _timed(phases: dict[str, float], name: str, function):
    started = time.perf_counter()
    value = function()
    phases[name] = time.perf_counter() - started
    return value


def benchmark(size: int) -> dict[str, object]:
    from deslopizator.complexity import analyze_complexity
    from deslopizator.duplication.detector import analyze_duplication_facts
    from deslopizator.history.churn import analyze_churn
    from deslopizator.history.coupling import analyze_coupling
    from deslopizator.imports.graph import analyze_imports
    from deslopizator.inventory.classifier import discover_project
    from deslopizator.smells.analysis import analyze_smells

    phases: dict[str, float] = {}
    with tempfile.TemporaryDirectory(prefix=f"deslop-benchmark-{size}-") as directory:
        root = Path(directory)
        _generate(root, size)
        inventory = _timed(phases, "discovery", lambda: discover_project(root))
        _timed(phases, "complexity", lambda: analyze_complexity(inventory))
        _timed(phases, "duplication", lambda: analyze_duplication_facts(inventory))
        imports = _timed(phases, "imports", lambda: analyze_imports(inventory))
        _timed(phases, "smells", lambda: analyze_smells(inventory))
        _timed(phases, "git_analysis", lambda: (analyze_churn(inventory), analyze_coupling(inventory, imports)))
    phases["total"] = sum(phases.values())
    return {"files": size, "seconds": phases}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000])
    arguments = parser.parse_args(argv)
    _load_package()
    print(json.dumps([benchmark(size) for size in arguments.sizes], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
