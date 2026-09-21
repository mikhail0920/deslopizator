import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedImport:
    raw_import: str
    line: int
    kind: str
    module: str | None
    level: int
    names: tuple[str, ...]


def _is_type_checking_test(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "TYPE_CHECKING"
        and isinstance(node.value, ast.Name)
        and node.value.id == "typing"
    )


def _from_raw_import(node: ast.ImportFrom, names: tuple[str, ...]) -> str:
    prefix = "." * node.level
    module = node.module or ""
    imported = ",".join(names)
    if module:
        return f"{prefix}{module}"
    return f"{prefix}{imported}"


class ImportCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: list[ParsedImport] = []
        self._kind = "runtime"

    def visit_If(self, node: ast.If) -> None:
        previous = self._kind
        if _is_type_checking_test(node.test):
            self._kind = "type_checking"
            for statement in node.body:
                self.visit(statement)
            self._kind = previous
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ParsedImport(alias.name, node.lineno, self._kind, alias.name, 0, ()))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        names = tuple(alias.name for alias in node.names)
        self.imports.append(ParsedImport(_from_raw_import(node, names), node.lineno, self._kind, node.module, node.level, names))


def parse_file(path: Path) -> tuple[ParsedImport, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    collector = ImportCollector()
    collector.visit(tree)
    return tuple(collector.imports)
