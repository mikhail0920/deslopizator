from pathlib import Path

from deslopizator.history.coupling import (
    _parse_commit_file_sets,
    build_couplings,
    static_dependency_pairs,
)
from deslopizator.history.models import ChangeCoupling
from deslopizator.imports.graph import analyze_imports
from deslopizator.inventory.classifier import discover_project


def test_coupling_probabilities_and_strength():
    commits = [{"a.py", "b.py"} for _ in range(7)]
    commits.extend({"a.py"} for _ in range(3))
    commits.append({"b.py"})

    result = build_couplings(commits)

    assert result == (
        ChangeCoupling("a.py", "b.py", 10, 8, 7, 0.7, 0.875, 0.7, False),
    )


def test_coupling_below_cochanges_threshold_is_absent():
    commits = [{"a.py", "b.py"} for _ in range(4)]
    commits.extend({"a.py"} for _ in range(2))
    commits.extend({"b.py"} for _ in range(2))

    assert build_couplings(commits) == ()


def test_coupling_below_strength_threshold_is_absent():
    commits = [{"a.py", "b.py"} for _ in range(6)]
    commits.extend({"a.py"} for _ in range(4))
    commits.extend({"b.py"} for _ in range(4))

    assert build_couplings(commits) == ()


def test_static_dependency_is_detected_in_either_direction(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.py").write_text("from . import b\n", encoding="utf-8")
    (source / "b.py").write_text("value = 1\n", encoding="utf-8")
    inventory = discover_project(tmp_path)
    imports = analyze_imports(inventory)

    pairs = static_dependency_pairs(inventory, imports.edges)

    assert frozenset((str(source / "a.py"), str(source / "b.py"))) in pairs


def test_coupling_without_import_edge_is_marked_temporal_only():
    result = build_couplings([{"a.py", "b.py"}] * 5)

    assert result[0].has_static_dependency is False


def test_coupling_with_import_edge_is_not_marked_temporal_only():
    dependency = {frozenset(("a.py", "b.py"))}

    result = build_couplings([{"a.py", "b.py"}] * 5, static_dependencies=dependency)

    assert result[0].has_static_dependency is True


def test_coupling_order_is_stable_and_pairs_are_unique():
    commits = [{"z.py", "a.py", "b.py"}] * 5

    result = build_couplings(commits)

    assert [(item.file_a, item.file_b) for item in result] == [("a.py", "b.py"), ("a.py", "z.py"), ("b.py", "z.py")]
    assert all(item.file_a < item.file_b for item in result)


def test_merge_commit_is_counted_as_an_ordinary_commit():
    merge_output = (
        "0123456789abcdef0123456789abcdef01234567\t1700000000\n"
        "1\t1\ta.py\n"
        "1\t1\tb.py\n"
    )

    commits = _parse_commit_file_sets(merge_output)

    assert len(commits) == 1
    assert commits[0].paths == frozenset({"a.py", "b.py"})
