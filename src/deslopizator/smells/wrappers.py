import ast

from deslopizator.smells.models import Finding, ParsedFile, ParsedFunction, PassThrough, SmellConfig, make_finding


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _is_protocol_method(function: ParsedFunction, protocols: set[str]) -> bool:
    return function.class_name in protocols


def _ignored(function: ParsedFunction, protocols: set[str]) -> bool:
    name = function.node.name
    decorators = {_decorator_name(item) for item in function.node.decorator_list}
    return (
        name.startswith("__") and name.endswith("__")
        or bool(decorators & {"property", "override", "abstractmethod"})
        or _is_protocol_method(function, protocols)
    )


def _meaningful_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            body.pop(0)
    return body


def _name(node: ast.expr) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _call_target(call: ast.Call) -> tuple[str, str, str | None, str | None] | None:
    if isinstance(call.func, ast.Attribute):
        if isinstance(call.func.value, ast.Name):
            return f"{call.func.value.id}.{call.func.attr}", call.func.attr, call.func.value.id, call.func.attr
        if isinstance(call.func.value, ast.Attribute) and isinstance(call.func.value.value, ast.Name):
            owner = f"{call.func.value.value.id}.{call.func.value.attr}"
            return f"{owner}.{call.func.attr}", call.func.attr, call.func.value.attr, call.func.attr
        return None
    if isinstance(call.func, ast.Name):
        return call.func.id, call.func.id, None, None
    return None


def _parameter_names(function: ParsedFunction) -> tuple[str, ...]:
    arguments = function.node.args
    names = [item.arg for item in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]]
    if function.class_name and names and names[0] in {"self", "cls"}:
        names.pop(0)
    if arguments.vararg or arguments.kwarg:
        return ()
    return tuple(names)


def _forwards_arguments(call: ast.Call, expected: tuple[str, ...]) -> bool:
    if len(call.args) != len(expected) or call.keywords and len(call.keywords) != len(expected):
        return False
    if call.keywords:
        if any(item.arg is None for item in call.keywords):
            return False
        return all(item.arg == expected[index] and _name(item.value) == expected[index] for index, item in enumerate(call.keywords))
    return all(_name(argument) == expected[index] for index, argument in enumerate(call.args))


def find_pass_throughs(files: tuple[ParsedFile, ...]) -> tuple[PassThrough, ...]:
    protocols = {
        cls.name
        for file in files
        for cls in file.classes
        if any(isinstance(base, ast.Name) and base.id == "Protocol" for base in cls.bases)
    }
    found: list[PassThrough] = []
    for file in files:
        for function in file.functions:
            if _ignored(function, protocols):
                continue
            body = _meaningful_body(function.node)
            if len(body) != 1 or not isinstance(body[0], ast.Return) or not isinstance(body[0].value, ast.Call):
                continue
            target = _call_target(body[0].value)
            if target is None or not _forwards_arguments(body[0].value, _parameter_names(function)):
                continue
            target_text, target_name, owner_attribute, target_attribute = target
            found.append(PassThrough(function, target_text, target_name, target_attribute, owner_attribute))
    return tuple(found)


def findings_for_pass_throughs(pass_throughs: tuple[PassThrough, ...]) -> tuple[Finding, ...]:
    result = []
    for item in pass_throughs:
        function = item.function
        result.append(make_finding(
            "pass-through",
            function.relative_path,
            function.node.lineno,
            function.node.end_lineno,
            "high",
            {
                "function": function.qualified_name,
                "target": item.target,
                "arguments_forwarded": True,
            },
            function.qualified_name,
        ))
    return tuple(result)


def delegating_class_findings(
    files: tuple[ParsedFile, ...],
    pass_throughs: tuple[PassThrough, ...],
    config: SmellConfig,
) -> tuple[Finding, ...]:
    by_class: dict[tuple[str, str], list[PassThrough]] = {}
    classes: dict[tuple[str, str], ast.ClassDef] = {}
    for file in files:
        for cls in file.classes:
            key = (file.relative_path, cls.name)
            classes[key] = cls
    for item in pass_throughs:
        if item.function.class_name:
            by_class.setdefault((item.function.relative_path, item.function.class_name), []).append(item)
    findings = []
    for key, cls in classes.items():
        methods = [
            function for file in files if file.relative_path == key[0]
            for function in file.functions
            if function.class_name == key[1] and not function.node.name.startswith("_")
        ]
        wrappers = by_class.get(key, [])
        if len(methods) < config.delegating_class_min_methods or len(wrappers) / len(methods) < config.delegating_class_min_ratio:
            continue
        targets = {item.owner_attribute for item in wrappers if item.owner_attribute}
        if len(targets) != 1:
            continue
        target = next(iter(targets))
        findings.append(make_finding(
            "delegating-class", key[0], cls.lineno, cls.end_lineno, "high",
            {"class": cls.name, "methods": len(methods), "pass_through": len(wrappers), "target": f"self.{target}"},
            cls.name,
        ))
    return tuple(findings)
