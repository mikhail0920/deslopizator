import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from deslopizator.audit import analyze_project
from deslopizator.cli import audit, check, compare
from deslopizator.completeness.models import AnalysisStatus
from deslopizator.complexity import parse_python
from deslopizator.policy import AuditDiff, PolicyConfig, evaluate_diff
from deslopizator.snapshots import read_snapshot, write_snapshot


def project(root, files):
    root.mkdir(parents=True, exist_ok=True)
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return root


def eroded(name):
    return f"def {name}(x):\n" + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(11))


def test_missing_path_fails_check_and_audit(tmp_path):
    assert check(tmp_path / "missing", None) == 2
    assert audit(tmp_path / "missing") == 2


def test_module_cli_propagates_error_exit(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    run = subprocess.run([sys.executable, "-m", "deslopizator.cli", "check", str(tmp_path / "missing")], env=env, capture_output=True, text=True)
    assert run.returncode == 2
    assert "PASSED" not in run.stdout


@pytest.mark.parametrize("statement", ["from pkg import b, c", "from . import b, c"])
def test_all_imported_modules_participate_in_cycles(tmp_path, statement):
    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": statement, "pkg/b.py": "x = 1", "pkg/c.py": "from pkg import a"})
    result = analyze_project(tmp_path)
    assert result.imports.cycles[0].modules == ("pkg.a", "pkg.c")
    assert result.completeness.imports.status is AnalysisStatus.COMPLETE


def test_relative_from_package_resolves_child_module(tmp_path):
    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "from .sub import child", "pkg/sub/__init__.py": "", "pkg/sub/child.py": "from .. import a"})
    assert analyze_project(tmp_path).imports.cycles[0].modules == ("pkg.a", "pkg.sub.child")


def test_imports_use_all_source_roots(tmp_path):
    project(tmp_path, {"pyproject.toml": '[tool.deslop]\nsource-roots = ["one", "two"]\n', "one/a.py": "import b", "two/b.py": "import a"})
    result = analyze_project(tmp_path)
    assert result.imports.cycles[0].modules == ("a", "b")
    assert result.completeness.imports.status is AnalysisStatus.COMPLETE


def test_import_parse_errors_are_partial(tmp_path):
    project(tmp_path, {"broken.py": "def broken(:\n"})
    result = analyze_project(tmp_path)
    assert result.completeness.imports.status is AnalysisStatus.PARTIAL
    assert result.completeness.imports.reasons


def test_elif_does_not_lower_later_nesting(tmp_path):
    project(tmp_path, {"app.py": "def f(x):\n    if x == 1:\n        pass\n    elif x == 2:\n        pass\n    if x:\n        if x > 3:\n            pass\n"})
    assert parse_python(tmp_path / "app.py")[0].max_nesting == 2


def test_duplication_density_ignores_comment_and_blank_lines(tmp_path):
    source = "def f(x):\n" + "".join(f"    x += {i}\n" for i in range(30)) + "    return x\n"
    project(tmp_path, {"a.py": source, "b.py": source})
    before = analyze_project(tmp_path)
    spaced = source.replace("\n", "\n# comment\n\n\n")
    project(tmp_path, {"a.py": spaced, "b.py": spaced})
    after = analyze_project(tmp_path)
    assert after.duplication.duplication_density == before.duplication.duplication_density == 1
    assert after.duplication.duplicated_lines == before.duplication.duplicated_lines
    assert AuditDiff(before, after).new_clone_groups == 0


def test_replacing_eroded_function_is_a_new_problem(tmp_path):
    before = analyze_project(project(tmp_path / "before", {"app.py": eroded("old")}))
    after = analyze_project(project(tmp_path / "after", {"app.py": eroded("new")}))
    difference = AuditDiff(before, after)
    assert difference.new_eroded_functions == 1
    assert not evaluate_diff(difference, PolicyConfig()).passed


def test_eroded_identity_survives_checkout_and_line_changes(tmp_path):
    before = analyze_project(project(tmp_path / "before", {"app.py": eroded("same")}))
    after = analyze_project(project(tmp_path / "after", {"app.py": "# header\n\n" + eroded("same")}))
    assert AuditDiff(before, after).new_eroded_functions == 0


def test_replacing_cycle_is_a_new_problem(tmp_path):
    before = analyze_project(project(tmp_path / "before", {"a.py": "import b", "b.py": "import a"}))
    after = analyze_project(project(tmp_path / "after", {"c.py": "import d", "d.py": "import c"}))
    assert AuditDiff(before, after).new_cycle_groups == 1


def test_replacing_clone_structure_is_a_new_problem(tmp_path):
    old = "def f(x):\n" + "    x += 1\n" * 40
    new = old.replace("+=", "*=")
    before = analyze_project(project(tmp_path / "before", {"a.py": old, "b.py": old}))
    after = analyze_project(project(tmp_path / "after", {"a.py": new, "b.py": new}))
    assert before.duplication.clone_group_count == after.duplication.clone_group_count == 1
    assert AuditDiff(before, after).new_clone_groups == 1


def test_partial_baseline_does_not_block_when_current_is_complete(tmp_path):
    before = analyze_project(project(tmp_path / "before", {"app.py": "def broken(:"}))
    after = analyze_project(project(tmp_path / "after", {"app.py": "x=1"}))
    assert evaluate_diff(AuditDiff(before, after), PolicyConfig()).passed


def test_snapshots_are_portable_deterministic_and_roundtrip(tmp_path):
    code = eroded("f")
    files = {"a.py": code, "b.py": code}
    before = analyze_project(project(tmp_path / "one", files))
    after = analyze_project(project(tmp_path / "two", files))
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    write_snapshot(before, first)
    write_snapshot(after, second)
    assert first.read_bytes() == second.read_bytes()
    loaded = read_snapshot(first)
    assert loaded.inventory.root == "."
    assert loaded.score == before.score
    assert loaded.duplication == before.duplication
    assert loaded.clone_groups[0].fingerprint == before.clone_groups[0].fingerprint
    assert AuditDiff(before, loaded).new_eroded_functions == 0
    write_snapshot(loaded, second)
    assert first.read_bytes() == second.read_bytes()
    assert compare(first, second) == 0


def test_cli_json_and_compare(tmp_path):
    project(tmp_path / "project", {"app.py": "x = 1"})
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    snapshot = tmp_path / "report.json"
    run = subprocess.run([sys.executable, "-m", "deslopizator.cli", "audit", str(tmp_path / "project"), "--json", str(snapshot)], env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    run = subprocess.run([sys.executable, "-m", "deslopizator.cli", "compare", str(snapshot), str(snapshot)], env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "New eroded functions: 0" in run.stdout


def test_snapshot_versions_are_checked(tmp_path):
    result = analyze_project(project(tmp_path / "project", {"app.py": "x = 1"}))
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    write_snapshot(result, first)
    write_snapshot(replace(result, score=replace(result.score, version="future")), second)
    assert compare(first, second) == 2
    assert not evaluate_diff(AuditDiff(result, read_snapshot(second)), PolicyConfig()).passed
    first.write_text(json.dumps({"schema_version": 999}))
    with pytest.raises(ValueError, match="schema"):
        read_snapshot(first)


def test_git_baseline_check_reports_new_function(tmp_path, capsys):
    project(tmp_path, {"app.py": eroded("old")})
    def git(*arguments):
        subprocess.run(["git", "-C", str(tmp_path), *arguments], check=True, capture_output=True)
    git("init")
    git("add", "app.py")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "baseline")
    assert check(tmp_path, "HEAD") == 0
    project(tmp_path, {"app.py": eroded("new")})
    assert check(tmp_path, "HEAD") == 1
    output = capsys.readouterr().out
    assert "max-new-eroded-functions" in output
    assert " -> " in output


def test_check_against_legacy_baseline_allows_same_architecture_violation(tmp_path):
    project(
        tmp_path,
        {
            "pyproject.toml": """[tool.deslop]
source-roots = ["."]

[[tool.deslop.architecture.layers]]
name = "domain"
include = ["app.domain.**"]
[[tool.deslop.architecture.layers]]
name = "infra"
include = ["app.infrastructure.**"]
[[tool.deslop.architecture.forbidden]]
from = "domain"
to = "infra"
""",
            "app/domain/order.py": "import app.infrastructure.database\n",
            "app/infrastructure/database.py": "value = 1\n",
        },
    )
    subprocess.run(["git", "-C", str(tmp_path), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "baseline"],
        check=True,
        capture_output=True,
    )
    (tmp_path / "app/domain/order.py").write_text("\nimport app.infrastructure.database\n", encoding="utf-8")

    assert check(tmp_path, "HEAD") == 0
