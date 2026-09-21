import argparse
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from deslopizator.audit import analyze_project
from deslopizator.policy import AuditDiff, evaluate, evaluate_diff, load_policy_config
from deslopizator.scoring import ScoringParameters
from deslopizator.snapshots import read_snapshot, write_snapshot
from deslopizator.snapshots import snapshot_document
from deslopizator.explain.catalog import rule_for


def _symbol(value: str, fallback: str) -> str:
    try:
        value.encode(sys.stdout.encoding or "utf-8")
    except (LookupError, UnicodeEncodeError):
        return fallback
    return value


def _sarif(result) -> dict:
    rules = {}
    results = []
    for finding in (result.smells.findings if result.smells else ()):
        code = {"pass-through": "DS101", "delegating-class": "DS102", "delegation-chain": "DS103", "single-implementation-abstraction": "DS104", "swallowed-exception": "DS105"}.get(finding.rule, finding.rule)
        rules.setdefault(code, {"id": code, "name": finding.rule})
        results.append({
            "ruleId": code,
            "level": "error" if finding.confidence == "certain" else "warning",
            "message": {"text": f"{finding.rule} ({finding.confidence} confidence)"},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": finding.path}, "region": {"startLine": finding.line, "endLine": finding.end_line}}}],
        })
    return {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json", "runs": [{"tool": {"driver": {"name": "deslopizator", "rules": list(rules.values())}}, "results": results}]}


def _print_finding(finding) -> None:
    code = {"pass-through": "DS101", "delegating-class": "DS102", "delegation-chain": "DS103", "single-implementation-abstraction": "DS104", "swallowed-exception": "DS105"}.get(finding.rule, finding.rule)
    title = {"pass-through": "pass-through-function", "delegating-class": "delegating-class", "delegation-chain": "delegation-chain", "single-implementation-abstraction": "single-implementation-abstraction", "swallowed-exception": "swallowed-exception"}.get(finding.rule, finding.rule)
    print(f"\n{code} {title}\n")
    print(f"{finding.path}:{finding.line}-{finding.end_line}\n")
    if finding.rule == "pass-through":
        print(f"{finding.facts.get('function', 'function')}() only forwards its arguments to {finding.facts.get('target', 'another call')}.")
    elif finding.rule == "delegating-class":
        print(f"{finding.facts.get('class', 'Class')} delegates most public methods to {finding.facts.get('target', 'one object')}.")
    elif finding.rule == "delegation-chain":
        print("Delegation chain: " + " -> ".join(finding.facts.get("chain", ())))
    elif finding.rule == "single-implementation-abstraction":
        implementation = finding.facts.get("implementations", ("unknown",))[0]
        print(f"{finding.facts.get('abstraction', 'Abstraction')} has 1 known implementation: {implementation}")
    else:
        print(f"Broad exception handling uses {finding.facts.get('fallback', 'a constant fallback')}.")
    print(f"\nConfidence: {finding.confidence}")
    explanation = rule_for(finding.rule)
    if explanation is not None:
        print(f"\nWhy:\n  {explanation.why}")
        print("\nAsk:")
        for question in explanation.questions:
            print(f"  {question}")
    else:
        print("\nWhy:\n  This code matches an observable slop pattern.")


def _print_smells(result, details: bool) -> None:
    findings = result.smells.findings if result.smells else ()
    labels = (
        ("pass-through functions", "pass-through"),
        ("delegation chains", "delegation-chain"),
        ("single-use abstractions", "single-implementation-abstraction"),
        ("swallowed exceptions", "swallowed-exception"),
    )
    print("\nSlop findings:")
    for label, rule in labels:
        print(f"  {label:<28} {sum(item.rule == rule for item in findings)}")
    if result.smells and result.smells.suppressed_findings:
        print(f"  suppressed findings{' ':<18} {result.smells.suppressed_findings}")
    if details:
        for finding in findings:
            _print_finding(finding)


def audit(path: Path, json_path: Path | None = None, details: bool = False, output_format: str = "text") -> int:
    try:
        result = analyze_project(path)
        if json_path is not None:
            write_snapshot(result, json_path)
    except Exception as exc:
        print(f"Analysis failed: {exc}")
        return 2
    if output_format == "json":
        print(json.dumps(snapshot_document(result), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if output_format == "sarif":
        print(json.dumps(_sarif(result), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
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
    print(f"\nStructural score: {total}")
    print(f"\nSlop Index: {total} / 100{partial}")
    print(f"Scoring: {score.version}")
    _print_smells(result, details)
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
    for file in result.complexity.files:
        for function in file.functions:
            if function.eroded:
                print(f"  {Path(file.path).relative_to(inventory.root)}:{function.line} {function.qualified_name} CC={function.complexity}")
    print("\nDuplication")
    print(f"Clone groups: {result.duplication.clone_group_count}")
    print(f"Duplicated lines: {result.duplication.duplicated_lines}")
    print(f"Duplication density: {result.duplication.duplication_density:.1%}")
    for group in result.clone_groups:
        print(f"  Clone ({group.token_count} tokens):")
        for instance in group.instances:
            print(f"    {Path(instance.path).relative_to(inventory.root)}:{instance.start_line}-{instance.end_line}")
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

    print("\nHotspots")
    if not result.git_available:
        print("  Git history unavailable; priorities are 0")
    shown = 0
    for hotspot in result.hotspots:
        if hotspot.priority <= 0:
            continue
        shown += 1
        relative = Path(hotspot.path).relative_to(inventory.root)
        print(f"\n  {shown}. {relative}")
        print(f"     debt: {hotspot.structural_debt:.2f}")
        print(f"     commits/180d: {hotspot.churn}")
        print(f"     priority: {hotspot.priority:.2f}")

    print("\nChange coupling")
    if not result.coupling_available:
        print("  Change coupling unavailable")
    for coupling in result.coupling:
        file_a = Path(coupling.file_a).relative_to(inventory.root).as_posix()
        file_b = Path(coupling.file_b).relative_to(inventory.root).as_posix()
        print(f"\n  {file_a} {_symbol('↔', '<->')} {file_b}")
        print(f"    changed together: {coupling.cochanges} times")
        arrow = _symbol("→", "->")
        print(f"    A {arrow} B: {coupling.probability_b_given_a:.0%}")
        print(f"    B {arrow} A: {coupling.probability_a_given_b:.0%}")
        print(f"    static dependency: {'yes' if coupling.has_static_dependency else 'no'}")
        if not coupling.has_static_dependency:
            print("    Strong temporal coupling detected.")
            print(
                f"    These files changed together in {coupling.strength:.0%}+ of their changes."
            )
            print("    No direct static dependency was found.")

    print("\nArchitecture")
    architecture = result.architecture
    if architecture is None or architecture.violation_count == 0:
        print("  0 violations")
    else:
        print(f"\n  {architecture.violation_count} violations")
        for violation in architecture.violations:
            arrow = _symbol("→", "->")
            print(f"\n  {violation.source_layer} {arrow} {violation.target_layer}")
            print(f"    {violation.source_module}")
            print(f"    imports {violation.target_module}")
            print(f"    line {violation.line}")
    return 0


def _audit_ref(path: Path, reference: str):
    root = path.resolve()
    command = ["git", "-C", str(root), "archive", reference]
    try:
        archive = subprocess.run(command, check=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"cannot read baseline {reference}: {exc}") from exc
    temporary = tempfile.TemporaryDirectory()
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as stream:
            stream.extractall(temporary.name, filter="data")
        return temporary, analyze_project(Path(temporary.name))
    except Exception:
        temporary.cleanup()
        raise


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
        print(f"Slop Index: {before} -> {after}")
    return 0 if policy.passed else 1


def diff(path: Path, reference: str) -> int:
    try:
        current = analyze_project(path)
        temporary, baseline = _audit_ref(path, reference)
        try:
            difference = AuditDiff(baseline, current)
            print(f"Slop Index: {baseline.score.total if baseline.score.total is not None else 'N/A'} -> {current.score.total if current.score.total is not None else 'N/A'}")
            print("\nNew slop")
            for finding in difference.new_slop:
                print(f"  {finding.rule}: {finding.path}:{finding.line}")
            print("\nResolved slop")
            for finding in difference.resolved_slop:
                print(f"  {finding.rule}: {finding.path}:{finding.line}")
        finally:
            temporary.cleanup()
    except Exception as exc:
        print(f"Analysis failed: {exc}")
        return 2
    return 0


def compare(before: Path, after: Path) -> int:
    try:
        baseline, current = read_snapshot(before), read_snapshot(after)
        if baseline.score.version != current.score.version:
            raise ValueError("incompatible scoring versions")
        difference = AuditDiff(baseline, current)
        print(f"Slop Index: {baseline.score.total} -> {current.score.total}")
        print(f"New eroded functions: {difference.new_eroded_functions}")
        print(f"New clone groups: {difference.new_clone_groups}")
        print(f"New cycle groups: {difference.new_cycle_groups}")
        print(f"New architecture violations: {difference.new_architecture_violations}")
        print(f"Resolved architecture violations: {difference.resolved_architecture_violations}")
        print(f"New slop: {len(difference.new_slop)}")
        print(f"Resolved slop: {len(difference.resolved_slop)}")
        if baseline.score.partial or current.score.partial:
            print("PARTIAL: comparison includes incomplete analysis")
        return 0
    except Exception as exc:
        print(f"Comparison failed: {exc}")
        return 2


def main():
    parser = argparse.ArgumentParser(description="A service for deterministic measurement of slop in the codebase.")
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    audit_parser = subparsers.add_parser("audit", help="Start audit directory")
    audit_parser.add_argument("path", type=Path, help="Path to directory to audit")
    audit_parser.add_argument("--json", type=Path, dest="json_path", help="Write a portable JSON snapshot")
    audit_parser.add_argument("--details", action="store_true", help="Show smell findings")
    audit_parser.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    compare_parser = subparsers.add_parser("compare", help="Compare two JSON snapshots")
    compare_parser.add_argument("before", type=Path)
    compare_parser.add_argument("after", type=Path)
    diff_parser = subparsers.add_parser("diff", help="Compare with a Git baseline")
    diff_parser.add_argument("reference", help="Git reference")
    diff_parser.add_argument("path", type=Path, nargs="?", default=Path("."))
    check_parser = subparsers.add_parser("check", help="Evaluate CI policy")
    check_parser.add_argument("path", type=Path, help="Path to directory to audit")
    check_parser.add_argument("--against", help="Git baseline reference")
    explain_parser = subparsers.add_parser("explain", help="Explain a smell rule")
    explain_parser.add_argument("rule")
    args = parser.parse_args()
    if args.cmd == "audit":
        return audit(args.path, args.json_path, args.details, args.format)
    if args.cmd == "compare":
        return compare(args.before, args.after)
    if args.cmd == "diff":
        return diff(args.path, args.reference)
    if args.cmd == "check":
        return check(args.path, args.against)
    if args.cmd == "explain":
        from deslopizator.explain.renderer import render_explanation
        try:
            print(render_explanation(args.rule))
        except KeyError:
            print(f"Unknown rule: {args.rule}")
            return 2
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
