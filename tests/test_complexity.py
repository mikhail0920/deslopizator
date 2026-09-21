from pathlib import Path

import pytest

from deslopizator.complexity import parse_python

def parse_code(tmp_path: Path, code: str):
    path = tmp_path / "example.py"
    path.write_text(code, encoding="utf-8")
    return parse_python(path)

def test_simple_function_has_complexity_one(tmp_path):
    results = parse_code(
        tmp_path,
        """
def foo():
    return 42
""",
    )

    assert len(results) == 1
    assert results[0].name == "foo"
    assert results[0].complexity == 1


def test_if_increases_complexity(tmp_path):
    results = parse_code(
        tmp_path,
        """
def foo(x):
    if x:
        return 1
    return 0
""",
    )

    assert results[0].complexity == 2


def test_elif_increases_complexity(tmp_path):
    results = parse_code(
        tmp_path,
        """
def foo(x):
    if x == 1:
        return 1
    elif x == 2:
        return 2
    return 0
""",
    )

    assert results[0].complexity == 3


def test_for_and_if_increase_complexity(tmp_path):
    results = parse_code(
        tmp_path,
        """
def foo(items):
    for item in items:
        if item:
            return item
""",
    )

    assert results[0].complexity == 3


def test_while_increases_complexity(tmp_path):
    results = parse_code(
        tmp_path,
        """
def foo():
    while True:
        break
""",
    )

    assert results[0].complexity == 2


def test_except_handlers_increase_complexity(tmp_path):
    results = parse_code(
        tmp_path,
        """
def foo():
    try:
        something()
    except ValueError:
        pass
    except TypeError:
        pass
""",
    )

    assert results[0].complexity == 3


def test_async_for_increases_complexity(tmp_path):
    results = parse_code(
        tmp_path,
        """
async def foo(items):
    async for item in items:
        pass
""",
    )

    assert results[0].complexity == 2


def test_nested_function_does_not_affect_outer_complexity(tmp_path):
    results = parse_code(
        tmp_path,
        """
def outer():
    if True:
        pass

    def inner():
        if True:
            pass
        if False:
            pass
""",
    )

    by_name = {result.name: result for result in results}

    assert by_name["outer"].complexity == 2
    assert by_name["inner"].complexity == 3


def test_method_inside_nested_class_does_not_affect_function(tmp_path):
    results = parse_code(
        tmp_path,
        """
def outer():
    class Foo:
        def method(self):
            if True:
                pass
            if False:
                pass
""",
    )

    by_name = {result.name: result for result in results}

    assert by_name["outer"].complexity == 1
    assert by_name["method"].complexity == 3


def test_function_line_numbers(tmp_path):
    results = parse_code(
        tmp_path,
        """

def foo():
    if True:
        return 1
""",
    )

    result = results[0]

    assert result.line == 3
    assert result.end_line == 5


def test_multiple_functions_are_returned(tmp_path):
    results = parse_code(
        tmp_path,
        """
def foo():
    pass

def bar(x):
    if x:
        pass
""",
    )

    by_name = {result.name: result for result in results}

    assert len(results) == 2
    assert by_name["foo"].complexity == 1
    assert by_name["bar"].complexity == 2


@pytest.mark.parametrize(
    ("construct", "expected"),
    [
        ("if x:\n        pass", 2),
        ("if x:\n        pass\n    elif y:\n        pass", 3),
        ("for item in items:\n        pass", 2),
        ("async for item in items:\n        pass", 2),
        ("while x:\n        pass", 2),
        ("try:\n        pass\n    except ValueError:\n        pass", 2),
        ("match value:\n        case 1:\n            pass\n        case 2:\n            pass", 3),
        ("match value:\n        case _:\n            pass", 1),
        ("result = value if condition else other", 2),
        ("if a and b and c:\n        pass", 4),
        ("if a or b:\n        pass", 3),
        ("values = [x for x in xs]", 2),
        ("values = [x for x in xs if x > 0]", 3),
        ("values = {x: x for x in xs if x > 0}", 3),
        ("values = (x for x in xs if x > 0)", 3),
    ],
)
def test_python_constructs_have_explicit_complexity(tmp_path, construct, expected):
    function_definition = "async def" if construct.startswith("async for") else "def"
    results = parse_code(
        tmp_path,
        f"{function_definition} foo(value, items, xs, a, b, c, condition, other):\n    {construct}\n",
    )

    assert results[0].complexity == expected


def test_combined_constructs_have_explicit_complexity(tmp_path):
    results = parse_code(
        tmp_path,
        """
def process(items, flag):
    for item in items:
        if item.active and flag:
            try:
                handle(item)
            except ValueError:
                recover(item)
""",
    )

    assert results[0].complexity == 5


def test_nested_function_and_lambda_do_not_affect_outer_complexity(tmp_path):
    results = parse_code(
        tmp_path,
        """
def outer(values):
    transform = lambda value: value if value else 0

    def inner(value):
        if value:
            pass
        return value

    return [inner(value) for value in values]
""",
    )

    by_name = {result.qualified_name: result for result in results}
    assert by_name["outer"].complexity == 2
    assert by_name["outer.inner"].complexity == 2


def test_class_method_and_nested_function_qualified_names(tmp_path):
    results = parse_code(
        tmp_path,
        """
class MyClass:
    def method(self):
        def helper():
            pass
        return helper()
""",
    )

    assert [result.qualified_name for result in results] == ["MyClass.method", "MyClass.method.helper"]


def test_parse_is_deterministic(tmp_path):
    code = """
def outer(value):
    if value and value > 0:
        return value

    def inner():
        return 0
"""

    assert parse_code(tmp_path, code) == parse_code(tmp_path, code)
