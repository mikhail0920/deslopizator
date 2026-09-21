import ast
import io
import tokenize
from dataclasses import dataclass
from pathlib import Path

from deslopizator.models import ComplexityMetrics, FileComplexityMetrics, FunctionMetrics


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


class NestingVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.depth = 0
        self.max_nesting = 0

    def _visit_nested(self, node: ast.AST) -> None:
        self.depth += 1
        self.max_nesting = max(self.max_nesting, self.depth)
        self.generic_visit(node)
        self.depth -= 1

    def visit_If(self, node: ast.If) -> None:
        self.depth += 1
        self.max_nesting = max(self.max_nesting, self.depth)
        self.visit(node.test)
        for statement in node.body:
            self.visit(statement)
        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            self.depth -= 1
            self.visit(node.orelse[0])
        else:
            for statement in node.orelse:
                self.visit(statement)
            self.depth -= 1

    def visit_For(self, node: ast.For) -> None:
        self._visit_nested(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_nested(node)

    def visit_While(self, node: ast.While) -> None:
        self._visit_nested(node)

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_nested(node)

    def visit_With(self, node: ast.With) -> None:
        self._visit_nested(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_nested(node)

    def visit_Match(self, node: ast.Match) -> None:
        self._visit_nested(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass


class StatementCounter(ast.NodeVisitor):
    def __init__(self) -> None:
        self.count = 0

    def visit(self, node: ast.AST) -> None:
        if isinstance(node, ast.stmt):
            self.count += 1
        super().visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass


class ReturnCounter(ast.NodeVisitor):
    def __init__(self) -> None:
        self.count = 0

    def visit_Return(self, node: ast.Return) -> None:
        self.count += 1
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass


def _docstring_lines(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[int]:
    if not node.body or not isinstance(node.body[0], ast.Expr):
        return set()
    expression = node.body[0].value
    if not isinstance(expression, ast.Constant) or not isinstance(expression.value, str):
        return set()
    return set(range(expression.lineno, expression.end_lineno + 1))


def _sloc(node: ast.FunctionDef | ast.AsyncFunctionDef, source: str) -> int:
    excluded = _docstring_lines(node)
    code_lines: set[int] = set()
    ignored = {tokenize.ENDMARKER, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in ignored:
            continue
        for line in range(token.start[0], token.end[0] + 1):
            if node.lineno <= line <= node.end_lineno and line not in excluded:
                code_lines.add(line)
    return len(code_lines)


def _parameter_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    arguments = node.args
    return len(arguments.posonlyargs) + len(arguments.args) + len(arguments.kwonlyargs) + bool(arguments.vararg) + bool(arguments.kwarg)


def _metrics_for(function: CollectedFunction, source: str, path: Path) -> FunctionMetrics:
    complexity = ComplexityVisitor()
    nesting = NestingVisitor()
    statements = StatementCounter()
    returns = ReturnCounter()
    for statement in function.node.body:
        complexity.visit(statement)
        nesting.visit(statement)
        statements.visit(statement)
        returns.visit(statement)
    return FunctionMetrics(
        path=str(path), name=function.node.name, qualified_name=function.qualified_name,
        line=function.node.lineno, end_line=function.node.end_lineno,
        complexity=complexity.complexity, sloc=_sloc(function.node, source),
        max_nesting=nesting.max_nesting, statement_count=statements.count,
        parameter_count=_parameter_count(function.node), return_count=returns.count,
    )


def parse_python(path: Path) -> list[FunctionMetrics]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    collector = FunctionCollector()
    collector.visit(tree)
    return [_metrics_for(function, source, path) for function in collector.functions]


def analyze_file(path: Path) -> FileComplexityMetrics:
    functions = tuple(parse_python(path))
    total_mass = sum(function.mass for function in functions)
    eroded_functions = tuple(function for function in functions if function.eroded)
    return FileComplexityMetrics(
        path=str(path), functions=functions, total_function_mass=total_mass,
        eroded_function_mass=sum(function.mass for function in eroded_functions),
        eroded_function_count=len(eroded_functions),
    )


parse_file = analyze_file


def analyze_complexity(paths_or_inventory) -> tuple[ComplexityMetrics, tuple[str, ...]]:
    if hasattr(paths_or_inventory, "production_files"):
        paths = [Path(file.path) for file in paths_or_inventory.production_files]
    else:
        paths = [Path(path) for path in paths_or_inventory]
    files: list[FileComplexityMetrics] = []
    errors: list[str] = []
    for raw_path in sorted(paths, key=str):
        try:
            files.append(analyze_file(raw_path))
        except (OSError, SyntaxError, UnicodeError) as error:
            errors.append(f"{raw_path}: {error}")
    file_tuple = tuple(files)
    functions = tuple(function for file in file_tuple for function in file.functions)
    metrics = ComplexityMetrics(
        files=file_tuple,
        function_count=len(functions),
        total_function_mass=sum(function.mass for function in functions),
        eroded_function_mass=sum(function.mass for function in functions if function.eroded),
        eroded_function_count=sum(function.eroded for function in functions),
    )
    return metrics, tuple(errors)
