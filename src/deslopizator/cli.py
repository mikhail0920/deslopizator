import argparse
from pathlib import Path

from deslopizator.audit import analyze_project
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


def main():
    parser = argparse.ArgumentParser(description="A service for deterministic measurement of slop in the codebase.")
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    audit_parser = subparsers.add_parser("audit", help="Start audit directory")
    audit_parser.add_argument("path", type=Path, help="Path to directory to audit")
    args = parser.parse_args()
    if args.cmd == "audit":
        audit(args.path)


if __name__ == "__main__":
    main()
