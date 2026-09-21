import ast

from deslopizator.smells.models import Finding, ParsedFile, make_finding


def _broad(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    return isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"}


def _fallback(handler: ast.ExceptHandler) -> str | None:
    body = handler.body
    if len(body) != 1:
        return None
    statement = body[0]
    if isinstance(statement, ast.Pass):
        return "pass"
    if isinstance(statement, ast.Continue):
        return "continue"
    if isinstance(statement, ast.Break):
        return "break"
    if isinstance(statement, ast.Return):
        value = statement.value
        if value is None:
            return "return"
        if isinstance(value, ast.Constant):
            return f"return {value.value!r}"
        if isinstance(value, (ast.List, ast.Dict, ast.Set, ast.Tuple)):
            return f"return {type(value).__name__.lower()}"
    return None


class _Collector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scope: list[str] = []
        self.items: list[tuple[ast.ExceptHandler, str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.items.append((node, ".".join(self.scope)))
        self.generic_visit(node)


def find_swallowed_exceptions(files: tuple[ParsedFile, ...]) -> tuple[Finding, ...]:
    findings = []
    for file in files:
        collector = _Collector()
        collector.visit(file.tree)
        for handler, scope in collector.items:
            fallback = _fallback(handler)
            if not _broad(handler) or fallback is None:
                continue
            handler_name = ast.unparse(handler.type) if handler.type is not None else "bare except"
            findings.append(make_finding(
                "swallowed-exception", file.relative_path, handler.lineno, handler.end_lineno, "high",
                {"handler": handler_name, "fallback": fallback, "function": scope or None},
                f"{scope}:{handler_name}:{fallback}",
            ))
    return tuple(findings)
