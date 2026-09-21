import argparse
from deslopizator.discovery import discover_code_files
from deslopizator.complexity import analyze_file
from pathlib import Path

def audit(path: Path) -> int:
    python_files = discover_code_files(path)
    for file in python_files:
        print(file.relative_to(path))
        metrics = analyze_file(file)
        for function in metrics.functions:
            print(f'\t{function.qualified_name:<20} CC {function.complexity:>2}  SLOC {function.sloc:<3} nesting {function.max_nesting}')
        print(f'\nFunctions: {len(metrics.functions)}')
        print(f'Eroded: {metrics.eroded_function_count}')
        print(f'Eroded mass: {metrics.eroded_mass_share:.1%}')

def main():
    parser = argparse.ArgumentParser(description="A service for deterministic measurement of slop in the codebase.")
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    audit_parser = subparsers.add_parser("audit", help="Start audit directory")
    audit_parser.add_argument("path", type=Path, help="Path to directory to audit")
    args = parser.parse_args()
    if args.cmd == "audit":
        audit(args.path)


if __name__ == '__main__':
    main()
