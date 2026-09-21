import argparse
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

from deslopizator.audit import analyze_project
from deslopizator.policy import AuditDiff, evaluate, evaluate_diff, load_policy_config
from deslopizator.scoring import ScoringParameters


def audit(path: Path) -> int:
    result = analyze_project(path)
    inventory = result.inventory
    print("Analysis\n")
    print(f"  Production files: {len(inventory.production_files)}")
    print(f"  Test files:       {len(inventory.test_files)}")
    print(f"  Generated files:  {len(inventory.generated_files)}")
    print(f"  Excluded files:   {len(inventory.excluded_files)}")
    print()
    for name, dimension in (
        ("Complexity", result.completeness.complexity),
        ("Duplication", result.completeness.duplication),
        ("Imports", result.completeness.imports),
    ):
        print(f"  {name:<14} {dimension.status.value}")

    score = result.score
    total = "N/A" if score.total is None else f"{score.total:.1f}"
    partial = " PARTIAL" if score.partial else ""
    print(f"\nSlop Index: {total} / 100{partial}")
    print(f"Scoring: {score.version}")
    parameters = ScoringParameters()
    for name, dimension, weight in (
        ("Complexity", score.complexity, parameters.complexity_weight),
        ("Duplication", score.duplication, parameters.duplication_weight),
        ("Cycles", score.cycles, parameters.cycles_weight),
    ):
        maximum = 100 * weight
        value = "N/A" if dimension is None else f"{maximum * dimension.score:.1f}"
        print(f"{name:<15}{value:>5} / {maximum:.0f}")
    partial_reasons = (
        ("Complexity", result.completeness.complexity.reasons),
        ("Duplication", result.completeness.duplication.reasons),
        ("Imports", result.completeness.imports.reasons),
    )
    if any(reasons for _, reasons in partial_reasons):
        print("\nPartial reasons:")
        for name, reasons in partial_reasons:
            for reason in reasons:
                print(f"  {name}: {reason}")

    print("\nComplexity")
    print(f"Functions: {result.complexity.function_count}")
    print(f"Eroded: {result.complexity.eroded_function_count}")
    if result.complexity.total_function_mass:
        share = result.complexity.eroded_function_mass / result.complexity.total_function_mass
    else:
        share = 0.0
    print(f"Eroded mass: {share:.1%}")
    print("\nDuplication")
    print(f"Clone groups: {result.duplication.clone_group_count}")
    print(f"Duplicated lines: {result.duplication.duplicated_lines}")
    print(f"Duplication density: {result.duplication.duplication_density:.1%}")
    print("\nImport cycles")
    for index, cycle in enumerate(result.imports.cycles, start=1):
        print(f"\n  Cycle {index}")
        for module in cycle.modules:
            print(f"    {module}")
    print(f"Modules: {result.imports.internal_module_count}")
    print(f"Runtime edges: {result.imports.runtime_edge_count}")
    print(f"Cyclic modules: {result.imports.modules_in_cycles}")
    print(f"Cycle density: {result.imports.cycle_density:.1%}")
    if result.imports.unresolved_import_count:
        print("\nAnalysis warnings:")
        print(f"  {result.imports.unresolved_import_count} unresolved imports")
    return 0


def _audit_ref(path: Path, reference: str):
    root = path.resolve()
    command = ["git", "-C", str(root), "archive", reference]
    try:
        archive = subprocess.run(command, check=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"cannot read baseline {reference}: {exc}") from exc
    temporary = tempfile.TemporaryDirectory()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as stream:
        stream.extractall(temporary.name)
    return temporary, analyze_project(Path(temporary.name))


def _print_policy(result, title: str = "Policy") -> None:
    print(f"{title}: {'PASSED' if result.passed else 'FAILED'}")
    if result.violations:
        print(f"\n{len(result.violations)} violations")
        for violation in result.violations:
            print(f"\n{violation.rule}")
            print(f"  allowed: {violation.expected}")
            print(f"  actual: {violation.actual}")
            print(f"  {violation.message}")


def check(path: Path, against: str | None) -> int:
    try:
        current = analyze_project(path)
        config = load_policy_config(path)
        if against is None:
            policy = evaluate(current, config)
        else:
            temporary, baseline = _audit_ref(path, against)
            try:
                policy = evaluate_diff(AuditDiff(baseline, current), config)
            finally:
                temporary.cleanup()
    except Exception as exc:
        print(f"Analysis failed: {exc}")
        return 2
    _print_policy(policy)
    if against is not None:
        before = "N/A" if baseline.score.total is None else f"{baseline.score.total:.1f}"
        after = "N/A" if current.score.total is None else f"{current.score.total:.1f}"
        print(f"Slop Index: {before} → {after}")
    return 0 if policy.passed else 1


def diff(path: Path, reference: str) -> int:
    try:
        current = analyze_project(path)
        temporary, baseline = _audit_ref(path, reference)
        try:
            print(f"Slop Index: {baseline.score.total if baseline.score.total is not None else 'N/A'} → {current.score.total if current.score.total is not None else 'N/A'}")
        finally:
            temporary.cleanup()
    except Exception as exc:
        print(f"Analysis failed: {exc}")
        return 2
    return 0


def main():
    parser = argparse.ArgumentParser(description="A service for deterministic measurement of slop in the codebase.")
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    audit_parser = subparsers.add_parser("audit", help="Start audit directory")
    audit_parser.add_argument("path", type=Path, help="Path to directory to audit")
    diff_parser = subparsers.add_parser("diff", help="Compare with a Git baseline")
    diff_parser.add_argument("reference", help="Git reference")
    diff_parser.add_argument("path", type=Path, nargs="?", default=Path("."))
    check_parser = subparsers.add_parser("check", help="Evaluate CI policy")
    check_parser.add_argument("path", type=Path, help="Path to directory to audit")
    check_parser.add_argument("--against", help="Git baseline reference")
    args = parser.parse_args()
    if args.cmd == "audit":
        return audit(args.path)
    if args.cmd == "diff":
        return diff(args.path, args.reference)
    if args.cmd == "check":
        return check(args.path, args.against)
    return 2


if __name__ == "__main__":
    main()
