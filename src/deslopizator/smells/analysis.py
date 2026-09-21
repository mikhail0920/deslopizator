import ast
import re
from pathlib import Path

from deslopizator.inventory.models import ProjectInventory
from deslopizator.smells.abstractions import find_single_implementation_abstractions
from deslopizator.smells.config import load_smell_config
from deslopizator.smells.delegation import delegation_chain_findings
from deslopizator.smells.exceptions import find_swallowed_exceptions
from deslopizator.smells.models import ParsedFile, ParsedFunction, SmellConfig, SmellMetrics
from deslopizator.smells.wrappers import delegating_class_findings, find_pass_throughs, findings_for_pass_throughs


_IGNORE_FILE = re.compile(r"deslop:\s*ignore-file\[([^]]+)\]")
_IGNORE_LINE = re.compile(r"deslop:\s*ignore\[([^]]+)\]")


class _Collector(ast.NodeVisitor):
    def __init__(self, path: str, relative_path: str, module: str | None) -> None:
        self.path = path
        self.relative_path = relative_path
        self.module = module
        self.scope: list[str] = []
        self.classes: list[ast.ClassDef] = []
        self.functions: list[ParsedFunction] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node)
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified = ".".join([*self.scope, node.name])
        self.functions.append(ParsedFunction(self.path, self.relative_path, self.module, node, qualified, self.scope[-1] if self.scope else None))
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)


def _suppressions(source: str) -> tuple[frozenset[str], tuple[tuple[int, frozenset[str]], ...]]:
    file_rules: set[str] = set()
    lines: list[tuple[int, frozenset[str]]] = []
    for number, line in enumerate(source.splitlines(), start=1):
        file_match = _IGNORE_FILE.search(line)
        if file_match:
            file_rules.update(item.strip() for item in file_match.group(1).split(","))
        line_match = _IGNORE_LINE.search(line)
        if line_match:
            lines.append((number, frozenset(item.strip() for item in line_match.group(1).split(","))))
    return frozenset(file_rules), tuple(lines)


def _parse(inventory: ProjectInventory) -> tuple[tuple[ParsedFile, ...], tuple[str, ...]]:
    root = Path(inventory.root)
    parsed: list[ParsedFile] = []
    errors: list[str] = []
    for source_file in sorted(inventory.production_files, key=lambda item: item.path):
        path = Path(source_file.path)
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as error:
            errors.append(f"{path}: {error}")
            continue
        collector = _Collector(str(path), path.relative_to(root).as_posix(), source_file.module)
        collector.visit(tree)
        ignore_file, ignore_lines = _suppressions(source)
        parsed.append(ParsedFile(str(path), collector.relative_path, source_file.module, source, tree, tuple(collector.functions), tuple(collector.classes), ignore_file, ignore_lines))
    return tuple(parsed), tuple(errors)


def _ignored(file: ParsedFile, finding) -> bool:
    aliases = {
        finding.rule,
        {"pass-through": "DS101", "delegating-class": "DS102", "delegation-chain": "DS103", "single-implementation-abstraction": "DS104", "swallowed-exception": "DS105"}.get(finding.rule),
    }
    for rule in file.ignore_file_rules:
        if rule in aliases or rule == "all":
            return True
    start = max(1, finding.line - 1)
    end = finding.end_line
    return any(start <= line <= end and (aliases & set(rules) or "all" in rules) for line, rules in file.ignore_lines)


def analyze_smells(inventory: ProjectInventory, config: SmellConfig | None = None) -> SmellMetrics:
    parsed, errors = _parse(inventory)
    config = config or load_smell_config(inventory.root)
    pass_throughs = find_pass_throughs(parsed)
    findings = []
    if config.pass_through:
        findings.extend(findings_for_pass_throughs(pass_throughs))
    if config.delegating_class and config.pass_through:
        findings.extend(delegating_class_findings(parsed, pass_throughs, config))
    if config.delegation_chain:
        findings.extend(delegation_chain_findings(parsed, pass_throughs, config))
    if config.single_implementation_abstraction:
        findings.extend(find_single_implementation_abstractions(parsed))
    if config.swallowed_exception:
        findings.extend(find_swallowed_exceptions(parsed))
    findings.sort(key=lambda finding: (finding.path, finding.line, finding.rule, finding.fingerprint))
    filtered = []
    suppressed = 0
    files_by_path = {file.relative_path: file for file in parsed}
    for finding in findings:
        file = files_by_path.get(finding.path)
        if file is not None and _ignored(file, finding):
            suppressed += 1
        else:
            filtered.append(finding)
    return SmellMetrics(tuple(filtered), suppressed, errors)
