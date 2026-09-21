import ast
from dataclasses import dataclass
from pathlib import Path

from deslopizator.models import FunctionComplexity


@dataclass(frozen=True)
class CollectedFunction:
    node: ast.FunctionDef | ast.AsyncFunctionDef
    qualified_name: str


class FunctionCollector(ast.NodeVisitor):
    """Collect functions and their lexical class/function scope."""

    def __init__(self) -> None:
        self.functions: list[CollectedFunction] = []
        self._scope: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._collect_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._collect_function(node)

    def _collect_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified_name = ".".join([*self._scope, node.name])
        self.functions.append(CollectedFunction(node, qualified_name))
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()


class ComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.complexity = 1

    def visit_If(self, node: ast.If) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self.visit(node.subject)
        for case in node.cases:
            if not self._is_wildcard_case(case):
                self.complexity += 1
            self.visit(case.pattern)
            if case.guard is not None:
                self.visit(case.guard)
            for statement in case.body:
                self.visit(statement)

    @staticmethod
    def _is_wildcard_case(case: ast.match_case) -> bool:
        return isinstance(case.pattern, ast.MatchAs) and case.pattern.name is None and case.pattern.pattern is None

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.complexity += 1
        self.visit(node.target)
        self.visit(node.iter)
        for condition in node.ifs:
            self.complexity += 1
            self.visit(condition)

    # Nested scopes have their own complexity. Their nodes are collected
    # separately and must not contribute to the containing function.
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass


def parse_python(path: Path) -> list[FunctionComplexity]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    collector = FunctionCollector()
    collector.visit(tree)

    results = []
    for function in collector.functions:
        visitor = ComplexityVisitor()
        for statement in function.node.body:
            visitor.visit(statement)
        results.append(
            FunctionComplexity(
                path=str(path),
                name=function.node.name,
                qualified_name=function.qualified_name,
                line=function.node.lineno,
                end_line=function.node.end_lineno,
                complexity=visitor.complexity,
            )
        )
    return results
