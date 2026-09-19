import argparse
from deslopizator.discovery import discover_code_files
from deslopizator.complexity import parse_python
from pathlib import Path

def audit(path: Path) -> int:
    python_files = discover_code_files(path)
    for file in python_files:
        print(file.relative_to(path))
        functions = parse_python(file)
        for func in functions:
            print(f'\t{func.name:<20} CC {func.complexity:<3}\tlines {func.line}-{func.end_line}')

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