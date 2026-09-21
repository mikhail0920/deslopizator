import ast

from deslopizator.smells.models import Finding, ParsedFile, PassThrough, SmellConfig, make_finding


def _class_methods(files: tuple[ParsedFile, ...]) -> dict[tuple[str, str], object]:
    result = {}
    for file in files:
        for function in file.functions:
            if function.class_name:
                result[(function.class_name, function.node.name)] = function
    return result


def _assigned_types(files: tuple[ParsedFile, ...]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for file in files:
        for cls in file.classes:
            for statement in cls.body:
                if not isinstance(statement, ast.FunctionDef) or statement.name != "__init__":
                    continue
                for node in ast.walk(statement):
                    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                        for target in node.targets:
                            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                                result[(cls.name, target.attr)] = node.value.func.id
                    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Attribute) and isinstance(node.target.value, ast.Name) and node.target.value.id == "self":
                        if isinstance(node.annotation, ast.Name):
                            result[(cls.name, node.target.attr)] = node.annotation.id
    return result


def _target_class(item: PassThrough, methods: dict, assigned: dict) -> str | None:
    function = item.function
    if item.owner_attribute and function.class_name:
        return assigned.get((function.class_name, item.owner_attribute))
    candidates = {class_name for class_name, method_name in methods if method_name == item.target_name}
    return next(iter(candidates)) if len(candidates) == 1 else None


def delegation_chain_findings(
    files: tuple[ParsedFile, ...],
    pass_throughs: tuple[PassThrough, ...],
    config: SmellConfig,
) -> tuple[Finding, ...]:
    methods = _class_methods(files)
    assigned = _assigned_types(files)
    by_function = {item.function: item for item in pass_throughs}
    links = {}
    for item in pass_throughs:
        class_name = _target_class(item, methods, assigned)
        if class_name is None:
            continue
        target = methods.get((class_name, item.target_name))
        if target is not None and target in by_function and target != item.function:
            links[item.function] = target

    findings = []
    seen: set[tuple[str, ...]] = set()
    for start in sorted(links, key=lambda function: (function.relative_path, function.qualified_name)):
        chain = [start]
        while chain[-1] in links and links[chain[-1]] not in chain:
            chain.append(links[chain[-1]])
        if len(chain) < config.delegation_chain_min_length:
            continue
        identity = tuple(f"{item.relative_path}:{item.qualified_name}" for item in chain)
        if identity in seen:
            continue
        seen.add(identity)
        findings.append(make_finding(
            "delegation-chain", start.relative_path, start.node.lineno, chain[-1].node.end_lineno, "high",
            {"chain": tuple(item.qualified_name for item in chain), "length": len(chain)},
            "->".join(identity),
        ))
    return tuple(findings)
