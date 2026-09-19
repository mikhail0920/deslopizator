from pathlib import Path
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