from pathlib import Path

from deslopizator.imports import analyze_imports


def make_project(tmp_path: Path, files: dict[str, str]):
    source_root = tmp_path / "src"
    paths = []
    for relative, source in files.items():
        path = source_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        paths.append(path)
    return source_root, paths


def test_two_module_runtime_cycle(tmp_path):
    root, paths = make_project(
        tmp_path,
        {
            "a.py": "from . import b\n",
            "b.py": "from . import a\n",
        },
    )

    analysis = analyze_imports(paths, root)

    assert analysis.cycles == (analysis.cycles[0],)
    assert analysis.cycles[0].modules == ("a", "b")
    assert analysis.metrics.cycle_group_count == 1
    assert analysis.metrics.modules_in_cycles == 2


def test_three_module_runtime_cycle_is_one_scc(tmp_path):
    root, paths = make_project(
        tmp_path,
        {
            "a.py": "from . import b\n",
            "b.py": "from . import c\n",
            "c.py": "from . import a\n",
        },
    )

    analysis = analyze_imports(paths, root)

    assert analysis.cycles == (analysis.cycles[0],)
    assert analysis.cycles[0].modules == ("a", "b", "c")


def test_acyclic_graph_has_no_cycles(tmp_path):
    root, paths = make_project(
        tmp_path,
        {
            "a.py": "from . import b\n",
            "b.py": "from . import c\n",
            "c.py": "value = 1\n",
        },
    )

    analysis = analyze_imports(paths, root)

    assert analysis.cycles == ()
    assert analysis.metrics.cycle_density == 0.0


def test_type_checking_import_does_not_create_runtime_cycle(tmp_path):
    root, paths = make_project(
        tmp_path,
        {
            "a.py": "if TYPE_CHECKING:\n    from . import b\n",
            "b.py": "from . import a\n",
        },
    )

    analysis = analyze_imports(paths, root)

    assert analysis.cycles == ()
    assert analysis.metrics.runtime_edge_count == 1
    assert analysis.metrics.type_checking_edge_count == 1


def test_typing_type_checking_is_classified_separately(tmp_path):
    root, paths = make_project(
        tmp_path,
        {
            "a.py": "import typing\nif typing.TYPE_CHECKING:\n    from . import b\n",
            "b.py": "value = 1\n",
        },
    )

    analysis = analyze_imports(paths, root)

    assert [(edge.target, edge.kind) for edge in analysis.edges] == [("b", "type_checking")]


def test_import_inside_function_is_runtime(tmp_path):
    root, paths = make_project(
        tmp_path,
        {
            "a.py": "def load():\n    from . import b\n",
            "b.py": "value = 1\n",
        },
    )

    analysis = analyze_imports(paths, root)

    assert analysis.edges[0].kind == "runtime"
    assert analysis.edges[0].line == 2


def test_relative_imports_nested_packages_and_init_module(tmp_path):
    root, paths = make_project(
        tmp_path,
        {
            "app/__init__.py": "from . import orders\n",
            "app/orders.py": "from .payments import pay\nfrom ..domain import User\n",
            "app/payments.py": "value = 1\n",
            "domain.py": "class User: pass\n",
        },
    )

    analysis = analyze_imports(paths, root)
    edges = {(edge.source, edge.target) for edge in analysis.edges}

    assert "app" in {edge.source for edge in analysis.edges}
    assert ("app", "app.orders") in edges
    assert ("app.orders", "app.payments") in edges
    assert ("app.orders", "domain") in edges


def test_absolute_import_forms_resolve_internal_modules(tmp_path):
    root, paths = make_project(
        tmp_path,
        {
            "app.py": "import foo\nimport foo.bar\nfrom foo import bar\nfrom foo.bar import baz\n",
            "foo/__init__.py": "value = 1\n",
            "foo/bar.py": "value = 1\n",
        },
    )

    analysis = analyze_imports(paths, root)

    assert [(edge.target, edge.line) for edge in analysis.edges] == [
        ("foo", 1),
        ("foo.bar", 2),
        ("foo.bar", 3),
        ("foo.bar", 4),
    ]


def test_external_imports_are_ignored(tmp_path):
    root, paths = make_project(
        tmp_path,
        {
            "app.py": "import requests\nimport numpy\nfrom pydantic import BaseModel\n",
        },
    )

    analysis = analyze_imports(paths, root)

    assert analysis.edges == ()
    assert analysis.unresolved == ()


def test_unresolved_relative_import_is_reported(tmp_path):
    root, paths = make_project(tmp_path, {"app.py": "from .missing import value\n"})

    analysis = analyze_imports(paths, root)

    assert len(analysis.unresolved) == 1
    assert analysis.unresolved[0].source == "app"
    assert analysis.unresolved[0].raw_import == ".missing"
    assert analysis.unresolved[0].line == 1


def test_self_import_is_a_cycle(tmp_path):
    root, paths = make_project(tmp_path, {"a.py": "from . import a\n"})

    analysis = analyze_imports(paths, root)

    assert analysis.cycles[0].modules == ("a",)


def test_metrics_and_cycles_have_deterministic_order(tmp_path):
    root, paths = make_project(
        tmp_path,
        {
            "z.py": "from . import y\n",
            "y.py": "from . import z\n",
            "a.py": "from . import b\n",
            "b.py": "from . import a\n",
        },
    )

    first = analyze_imports(list(reversed(paths)), root)
    second = analyze_imports(paths, root)

    assert first == second
    assert [cycle.modules for cycle in first.cycles] == [("a", "b"), ("y", "z")]
    assert first.metrics.cycle_density == 1.0
