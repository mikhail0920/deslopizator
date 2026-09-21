from pathlib import Path

import pytest

from deslopizator.duplication import analyze_duplication, detect_clones, normalize_source


def write_file(tmp_path: Path, name: str, source: str) -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def repeated_block(function_name: str, variable: str = "value", string: str = "hello", number: int = 42) -> str:
    operators = ["+", "-", "*", "/", "%", "//", "**"]
    lines = [f"def {function_name}():"]
    for index in range(22):
        operator = operators[index % len(operators)]
        lines.append(f"    {variable}{index} = left{index} {operator} right{index}")
        lines.append(f"    text{index} = {string!r}")
        lines.append(f"    number{index} = {number + index}")
    lines.append(f"    return {variable}0")
    return "\n".join(lines) + "\n"


def operator_block(function_name: str, operator: str) -> str:
    lines = [f"def {function_name}():"]
    for index in range(16):
        lines.append(f"    value{index} = left{index} {operator} right{index}")
    lines.append("    return value0")
    return "\n".join(lines) + "\n"


def control_flow_block(function_name: str, keyword: str) -> str:
    lines = [f"def {function_name}():"]
    for index in range(30):
        if keyword == "if":
            lines.append(f"    if condition{index}: pass")
        else:
            lines.append(f"    for item{index} in items{index}: pass")
    return "\n".join(lines) + "\n"


def test_tokenizer_normalizes_names_literals_and_preserves_keywords():
    tokens = normalize_source(
        """
# comment
def foo(user):
    if user:
        result = "hello"
        count = 42
        data = b"abc"
        return result
"""
    )

    values = [token.value for token in tokens]
    assert "foo" not in values
    assert values.count("NAME") >= 7
    assert "def" in values
    assert "if" in values
    assert "return" in values
    assert "STRING" in values
    assert "NUMBER" in values
    assert "BYTES" in values
    assert all(token.line > 0 and token.column >= 0 for token in tokens)


def test_comments_whitespace_and_renamed_variables_match(tmp_path):
    first = write_file(tmp_path, "a.py", repeated_block("first", "value", "hello", 42))
    second_source = repeated_block("second", "renamed", "world", 99).replace("    ", "        ")
    second_source = second_source.replace("\n        ", "\n        # comment\n\n        ", 1)
    second = write_file(tmp_path, "b.py", second_source)

    groups = detect_clones([first, second])

    assert len(groups) == 1
    assert groups[0].token_count >= 100
    assert {instance.path for instance in groups[0].instances} == {str(first), str(second)}


def test_exact_copy_paste_is_detected(tmp_path):
    first = write_file(tmp_path, "a.py", repeated_block("first"))
    second = write_file(tmp_path, "b.py", repeated_block("second"))

    groups = detect_clones([first, second])

    assert groups[0].instances[0].start_line == 1
    assert groups[0].instances[1].start_line == 1


def test_changed_operators_do_not_match(tmp_path):
    first_source = operator_block("first", "+")
    second_source = operator_block("second", "-")
    first = write_file(tmp_path, "a.py", first_source)
    second = write_file(tmp_path, "b.py", second_source)

    assert detect_clones([first, second]) == ()


def test_changed_control_flow_keyword_does_not_match(tmp_path):
    first = write_file(tmp_path, "a.py", control_flow_block("first", "if"))
    second = write_file(tmp_path, "b.py", control_flow_block("second", "for"))

    assert detect_clones([first, second]) == ()


def test_same_file_clone_is_detected(tmp_path):
    path = write_file(tmp_path, "same.py", repeated_block("first") + repeated_block("second"))

    groups = detect_clones([path])

    assert len(groups) == 1
    assert len(groups[0].instances) == 2
    assert groups[0].instances[0].start_line < groups[0].instances[1].start_line


def test_one_clone_group_can_have_more_than_two_instances(tmp_path):
    paths = [write_file(tmp_path, f"{name}.py", repeated_block(name)) for name in ("a", "b", "c")]

    groups = detect_clones(paths)

    assert len(groups) == 1
    assert len(groups[0].instances) == 3


def test_clone_shorter_than_minimum_is_ignored(tmp_path):
    short = "def first():\n    " + "\n    ".join(f"value{index} = {index}" for index in range(10)) + "\n"
    first = write_file(tmp_path, "a.py", short)
    second = write_file(tmp_path, "b.py", short.replace("first", "second"))

    assert detect_clones([first, second]) == ()


def test_overlapping_windows_are_one_maximal_clone(tmp_path):
    path = write_file(tmp_path, "same.py", repeated_block("first") + repeated_block("second"))

    groups = detect_clones([path])

    assert len(groups) == 1
    assert groups[0].token_count >= 100


def test_clone_instances_and_groups_are_stably_sorted(tmp_path):
    z_file = write_file(tmp_path, "z.py", repeated_block("z"))
    a_file = write_file(tmp_path, "a.py", repeated_block("a"))

    groups = detect_clones([z_file, a_file])

    assert groups == tuple(sorted(groups, key=lambda group: (group.instances[0].path, group.instances[0].start_line, group.instances[0].end_line, -group.token_count)))
    assert groups[0].instances == tuple(sorted(groups[0].instances, key=lambda item: (item.path, item.start_line, item.end_line)))


def test_aggregate_counts_unique_duplicated_lines_and_density(tmp_path):
    first = write_file(tmp_path, "a.py", repeated_block("first"))
    second = write_file(tmp_path, "b.py", repeated_block("second"))

    groups, metrics = analyze_duplication([first, second])

    assert groups
    assert metrics.clone_group_count == 1
    assert metrics.clone_instance_count == 2
    assert metrics.duplicated_lines == 136
    assert metrics.production_sloc == 136
    assert metrics.duplication_density == pytest.approx(1.0)


def test_empty_production_has_zero_density(tmp_path):
    first = write_file(tmp_path, "a.py", "# comment\n\n")

    _, metrics = analyze_duplication([first])

    assert metrics.production_sloc == 0
    assert metrics.duplication_density == 0.0
