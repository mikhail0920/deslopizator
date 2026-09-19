import ast
from pathlib import Path
from deslopizator.models import FunctionComplexity

class ComplexityCounter(ast.NodeVisitor):
    def __init__(self):
        self.complexity = 1

    def visit_If(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        pass

    def visit_AsyncFunctionDef(self, node):
        pass

    def visit_ClassDef(self, node):
        pass

def parse_python(path: Path) -> list[FunctionComplexity]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    results = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            counter = ComplexityCounter()
            for sub_node in node.body:
                counter.visit(sub_node)
            results.append(FunctionComplexity(path=path, name=node.name, line=node.lineno, end_line=node.end_lineno, complexity=counter.complexity))
    return results