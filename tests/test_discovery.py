from pathlib import Path

from deslopizator.discovery import discover_code_files

import pytest


def test_discover_single_file(tmp_path: Path):
    file = tmp_path / 'foo.py'
    file.write_text("print('hello')")

    result = discover_code_files(tmp_path)

    assert result == [file]


def test_discover_files_recursivly(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()

    foo = tmp_path / "foo.py"
    bar = src / "bar.py"

    foo.write_text("")
    bar.write_text("")

    result = discover_code_files(tmp_path)

    assert result == sorted([foo, bar])

def test_ignores_non_python_files(tmp_path: Path):
    python_file = tmp_path / "foo.py"
    python_file.write_text("")

    (tmp_path / "README.md").write_text("")
    (tmp_path / "config.json").write_text("")

    result = discover_code_files(tmp_path)

    assert result == [python_file]

@pytest.mark.parametrize(
    "directory",
    [
        ".git",
        ".venv",
        "venv",
        "__pycache__",
    ],
)
def test_ignores_excluded_directories(tmp_path: Path, directory: str):
    ignored = tmp_path / directory
    ignored.mkdir()

    (ignored / "hidden.py").write_text("")

    visible = tmp_path / "visible.py"
    visible.write_text("")

    result = discover_code_files(tmp_path)

    assert result == [visible]

def test_accepts_python_file_as_input(tmp_path: Path):
    file = tmp_path / "foo.py"
    file.write_text("")

    result = discover_code_files(file)

    assert result == [file]

def test_returns_files_in_sorted_order(tmp_path: Path):
    b = tmp_path / "b.py"
    a = tmp_path / "a.py"
    c = tmp_path / "c.py"

    b.write_text("")
    a.write_text("")
    c.write_text("")

    result = discover_code_files(tmp_path)

    assert result == [a, b, c]