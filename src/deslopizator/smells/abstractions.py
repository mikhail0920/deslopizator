import ast

from deslopizator.smells.models import Finding, ParsedFile, make_finding


def _base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _is_abstract(cls: ast.ClassDef) -> bool:
    bases = {_base_name(base) for base in cls.bases}
    if bases & {"ABC", "Protocol", "ABCMeta"}:
        return True
    if any(keyword.arg == "metaclass" and _base_name(keyword.value) == "ABCMeta" for keyword in cls.keywords):
        return True
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_base_name(decorator) == "abstractmethod" for decorator in node.decorator_list)
        for node in cls.body
    )


def _inherits(name: str, bases: dict[str, tuple[str, ...]], abstraction: str, seen: set[str] | None = None) -> bool:
    seen = seen or set()
    if name in seen:
        return False
    seen.add(name)
    direct = bases.get(name, ())
    return abstraction in direct or any(_inherits(base, bases, abstraction, seen.copy()) for base in direct)


def find_single_implementation_abstractions(files: tuple[ParsedFile, ...]) -> tuple[Finding, ...]:
    classes = [cls for file in files for cls in file.classes]
    abstractions = [cls for cls in classes if _is_abstract(cls)]
    bases = {cls.name: tuple(name for name in (_base_name(base) for base in cls.bases) if name) for cls in classes}
    findings = []
    for abstraction in abstractions:
        implementations = [cls for cls in classes if cls is not abstraction and _inherits(cls.name, bases, abstraction.name)]
        unique = {cls.name: cls for cls in implementations}
        if len(unique) != 1:
            continue
        implementation = next(iter(unique))
        file = next(file for file in files if any(cls.name == implementation for cls in file.classes))
        findings.append(make_finding(
            "single-implementation-abstraction", file.relative_path, abstraction.lineno, abstraction.end_lineno, "medium",
            {"abstraction": abstraction.name, "implementations": (implementation,), "known_implementation_count": 1},
            abstraction.name,
        ))
    return tuple(findings)
