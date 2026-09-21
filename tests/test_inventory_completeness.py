from pathlib import Path

from deslopizator.audit import analyze_project
from deslopizator.completeness import AnalysisStatus
from deslopizator.inventory import FileKind, ProjectConfig, classify_path, discover_project, load_config


def write_project(tmp_path: Path, files: dict[str, str], pyproject: str | None = None) -> Path:
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if pyproject is not None:
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return tmp_path


def test_default_classification_and_missing_config(tmp_path):
    write_project(
        tmp_path,
        {
            "app.py": "value = 1\n",
            "tests/test_app.py": "value = 1\n",
            "generated.py": "value = 1\n",
        },
    )

    inventory = discover_project(tmp_path)
    kinds = {Path(file.path).relative_to(tmp_path).as_posix(): file.kind for file in inventory.files}

    assert load_config(tmp_path).source_roots == ("src",)
    assert kinds["app.py"] is FileKind.PRODUCTION
    assert kinds["tests/test_app.py"] is FileKind.TEST
    assert kinds["generated.py"] is FileKind.PRODUCTION


def test_config_source_roots_exclude_and_generated(tmp_path):
    write_project(
        tmp_path,
        {
            "src/app.py": "value = 1\n",
            "src/generated/output.py": "value = 1\n",
            "src/ignored.py": "value = 1\n",
            "tests/test_app.py": "value = 1\n",
        },
        """
[tool.deslop]
source-roots = ["src"]
exclude = ["src/ignored.py"]

[tool.deslop.classification]
generated = ["src/generated/**"]
""",
    )

    inventory = discover_project(tmp_path)
    by_path = {Path(file.path).relative_to(tmp_path).as_posix(): file for file in inventory.files}

    assert by_path["src/app.py"].module == "app"
    assert by_path["src/generated/output.py"].kind is FileKind.GENERATED
    assert by_path["src/ignored.py"].kind is FileKind.EXCLUDED
    assert by_path["tests/test_app.py"].kind is FileKind.TEST


def test_classification_is_stable_for_windows_and_posix_paths():
    config = ProjectConfig()

    assert classify_path("tests/test_app.py", config) is FileKind.TEST
    assert classify_path(r"tests\test_app.py", config) is FileKind.TEST
    assert classify_path("src/app_test.py", config) is FileKind.TEST
    assert classify_path(r"src\app_test.py", config) is FileKind.TEST


def test_test_changes_do_not_change_production_complexity(tmp_path):
    write_project(tmp_path, {"src/app.py": "def app():\n    return 1\n", "tests/test_app.py": "def test_app():\n    return 1\n"})
    before = analyze_project(tmp_path)
    (tmp_path / "tests/test_app.py").write_text("def test_app():\n    if True:\n        return 1\n    return 0\n", encoding="utf-8")
    after = analyze_project(tmp_path)

    assert before.complexity == after.complexity


def test_duplication_between_production_and_test_is_excluded(tmp_path):
    repeated = "\n".join(f"    value{index} = left{index} + right{index}" for index in range(10))
    write_project(tmp_path, {"src/app.py": f"def app():\n{repeated}\n", "tests/test_app.py": f"def test_app():\n{repeated}\n"})

    result = analyze_project(tmp_path)

    assert result.duplication.clone_group_count == 0


def test_cycle_between_test_modules_is_excluded(tmp_path):
    write_project(
        tmp_path,
        {
            "src/app.py": "value = 1\n",
            "tests/a.py": "from . import b\n",
            "tests/b.py": "from . import a\n",
        },
    )

    result = analyze_project(tmp_path)

    assert result.imports.cycle_group_count == 0
    assert result.imports.internal_module_count == 1


def test_generated_file_does_not_affect_core_metrics(tmp_path):
    write_project(
        tmp_path,
        {"src/app.py": "def app():\n    return 1\n", "src/generated/bad.py": "def broken(:\n    if x:\n        pass\n"},
        """
[tool.deslop]
source-roots = ["src"]
[tool.deslop.classification]
generated = ["src/generated/**"]
""",
    )

    result = analyze_project(tmp_path)

    assert result.inventory.generated_files
    assert result.completeness.complexity.status is AnalysisStatus.COMPLETE
    assert result.complexity.function_count == 1


def test_syntax_error_in_production_is_partial(tmp_path):
    write_project(tmp_path, {"src/broken.py": "def broken(:\n    pass\n"})

    result = analyze_project(tmp_path)

    assert result.completeness.complexity.status is AnalysisStatus.PARTIAL


def test_syntax_error_in_test_does_not_make_complexity_partial(tmp_path):
    write_project(tmp_path, {"src/app.py": "value = 1\n", "tests/test_bad.py": "def broken(:\n"})

    result = analyze_project(tmp_path)

    assert result.completeness.complexity.status is AnalysisStatus.COMPLETE


def test_external_import_is_complete_but_local_unresolved_is_partial(tmp_path):
    write_project(tmp_path, {"src/external.py": "import requests\n", "src/local.py": "from .missing import value\n"})

    result = analyze_project(tmp_path)

    assert result.completeness.imports.status is AnalysisStatus.PARTIAL
    assert any("local -> .missing" in reason for reason in result.completeness.imports.reasons)

    (tmp_path / "src/local.py").write_text("import requests\n", encoding="utf-8")
    complete = analyze_project(tmp_path)
    assert complete.completeness.imports.status is AnalysisStatus.COMPLETE


def test_no_production_files_are_not_applicable(tmp_path):
    write_project(tmp_path, {"tests/test_app.py": "value = 1\n"})

    result = analyze_project(tmp_path)

    assert result.completeness.complexity.status is AnalysisStatus.NOT_APPLICABLE
    assert result.completeness.duplication.status is AnalysisStatus.NOT_APPLICABLE
    assert result.completeness.imports.status is AnalysisStatus.NOT_APPLICABLE
