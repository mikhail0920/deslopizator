from math import sqrt
from pathlib import Path

import pytest

from deslopizator.complexity import analyze_file, parse_python


def parse_code(tmp_path: Path, code: str):
    path = tmp_path / "metrics.py"
    path.write_text(code, encoding="utf-8")
    return parse_python(path)


@pytest.mark.parametrize(
    ("code", "expected_sloc"),
    [
        (
            """
def example():
    # comment

    value = 1  # inline comment
    return value
""",
            3,
        ),
        (
            '''
def example():
    """doc line 1
    doc line 2
    """
    value = 1
    return value
''',
            3,
        ),
        (
            """
def example():
    value = (
        1 +
        2
    )
    return value
""",
            6,
        ),
        (
            '''
def example():
    text = """first
second
third"""
    return text
''',
            5,
        ),
        (
            """
@decorator
def example():
    return 1
""",
            2,
        ),
    ],
)
def test_sloc_counts_python_lines_only(tmp_path, code, expected_sloc):
    assert parse_code(tmp_path, code)[0].sloc == expected_sloc


@pytest.mark.parametrize(
    ("body", "expected_nesting"),
    [
        ("if condition:\n        pass", 1),
        ("if outer:\n        if inner:\n            pass", 2),
        (
            "for item in items:\n        if item:\n            try:\n                pass\n            except ValueError:\n                pass",
            3,
        ),
    ],
)
def test_max_nesting_counts_structural_blocks(tmp_path, body, expected_nesting):
    result = parse_code(tmp_path, f"def example(items):\n    {body}\n")[0]

    assert result.max_nesting == expected_nesting


def test_elif_does_not_add_nesting_level(tmp_path):
    result = parse_code(
        tmp_path,
        """
def example(value):
    if value == 1:
        pass
    elif value == 2:
        pass
""",
    )[0]

    assert result.max_nesting == 1


def test_statement_count_excludes_nested_functions_and_inner_classes(tmp_path):
    result = parse_code(
        tmp_path,
        """
def outer(value):
    if value:
        pass
    def inner():
        return 1
    class Inner:
        def method(self):
            return 2
    return value
""",
    )[0]

    assert result.statement_count == 5


def test_parameter_count_includes_all_parameter_kinds(tmp_path):
    result = parse_code(
        tmp_path,
        """
def example(a, /, b, *args, c, **kwargs):
    return a
""",
    )[0]

    assert result.parameter_count == 5


def test_return_count_excludes_nested_functions(tmp_path):
    results = parse_code(
        tmp_path,
        """
def outer():
    def inner():
        return 1
    if True:
        return 2
    return 3
""",
    )

    assert results[0].return_count == 2
    assert results[1].return_count == 1


def test_methods_and_async_functions_have_structural_metrics(tmp_path):
    results = parse_code(
        tmp_path,
        """
class Worker:
    async def run(self, value):
        if value:
            return value
        return None
""",
    )

    result = results[0]
    assert result.qualified_name == "Worker.run"
    assert result.parameter_count == 2
    assert result.return_count == 2
    assert result.max_nesting == 1


def test_mass_is_computed_from_complexity_and_sloc(tmp_path):
    result = parse_code(
        tmp_path,
        """
def example(value):
    if value:
        return value
    return 0
""",
    )[0]

    assert result.complexity == 2
    assert result.sloc == 4
    assert result.mass == pytest.approx(4.0)


def test_file_erosion_aggregates_function_mass(tmp_path):
    code = """
def simple():
    return 1

def eroded(value):
    if value: pass
    if value: pass
"""
    path = tmp_path / "metrics.py"
    path.write_text(code, encoding="utf-8")

    metrics = analyze_file(path)

    assert len(metrics.functions) == 2
    assert metrics.eroded_function_count == 0
    assert metrics.eroded_mass_share == 0.0


def test_file_erosion_share_for_function_over_cc_threshold(tmp_path):
    code = """
def simple():
    return 1

def eroded(value):
    if value: pass
    if value: pass
    if value: pass
    if value: pass
    if value: pass
    if value: pass
    if value: pass
    if value: pass
    if value: pass
    if value: pass
"""
    path = tmp_path / "metrics.py"
    path.write_text(code, encoding="utf-8")
    eroded_mass = 11 * sqrt(11)
    total_mass = sqrt(2) + eroded_mass

    metrics = analyze_file(path)

    assert metrics.eroded_function_count == 1
    assert metrics.eroded_function_mass == pytest.approx(eroded_mass)
    assert metrics.eroded_mass_share == pytest.approx(eroded_mass / total_mass)


def test_empty_file_has_zero_eroded_mass_share(tmp_path):
    path = tmp_path / "empty.py"
    path.write_text("# no functions\n", encoding="utf-8")

    metrics = analyze_file(path)

    assert metrics.functions == ()
    assert metrics.eroded_mass_share == 0.0
