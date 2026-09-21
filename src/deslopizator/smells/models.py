import ast
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    end_line: int
    confidence: str
    facts: dict[str, object]
    fingerprint: str


@dataclass(frozen=True)
class SmellMetrics:
    findings: tuple[Finding, ...] = ()
    suppressed_findings: int = 0
    errors: tuple[str, ...] = ()

    @property
    def finding_count(self) -> int:
        return len(self.findings)


@dataclass(frozen=True)
class SmellConfig:
    version: str = "1"
    pass_through: bool = True
    delegation_chain: bool = True
    single_implementation_abstraction: bool = True
    swallowed_exception: bool = True
    delegating_class: bool = True
    delegating_class_min_methods: int = 3
    delegating_class_min_ratio: float = 0.80
    delegation_chain_min_length: int = 3


@dataclass(frozen=True)
class ParsedFunction:
    path: str
    relative_path: str
    module: str | None
    node: ast.FunctionDef | ast.AsyncFunctionDef
    qualified_name: str
    class_name: str | None


@dataclass(frozen=True)
class ParsedFile:
    path: str
    relative_path: str
    module: str | None
    source: str
    tree: ast.Module
    functions: tuple[ParsedFunction, ...]
    classes: tuple[ast.ClassDef, ...]
    ignore_file_rules: frozenset[str]
    ignore_lines: tuple[tuple[int, frozenset[str]], ...]


@dataclass(frozen=True)
class PassThrough:
    function: ParsedFunction
    target: str
    target_name: str
    target_attribute: str | None
    owner_attribute: str | None


def make_finding(
    rule: str,
    path: str,
    line: int,
    end_line: int,
    confidence: str,
    facts: dict[str, object],
    identity: str,
) -> Finding:
    return Finding(rule, path, line, end_line, confidence, facts, f"{rule}:{path}:{identity}")
