from types import SimpleNamespace

import pytest

from deslopizator.architecture.evaluator import ArchitectureConfigError, evaluate_architecture
from deslopizator.architecture.models import (
    ArchitectureConfig,
    ArchitectureForbidden,
    ArchitectureIndependent,
    ArchitectureLayer,
    ArchitectureLayered,
)
from deslopizator.architecture.parser import load_architecture_config
from deslopizator.audit import analyze_project
from deslopizator.imports.models import ImportEdge
from deslopizator.inventory.models import FileKind, ProjectInventory, SourceFile
from deslopizator.policy import AuditDiff, PolicyConfig, evaluate, evaluate_diff, load_policy_config
from deslopizator.completeness.models import AuditCompleteness, DimensionCompleteness, AnalysisStatus
from deslopizator.scoring.models import SlopScore


def inventory(*modules: str) -> ProjectInventory:
    return ProjectInventory(
        ".",
        tuple(SourceFile(f"{module.replace('.', '/')}.py", module, FileKind.PRODUCTION) for module in modules),
        (".",),
    )


def test_forbidden_domain_to_infrastructure_is_a_violation():
    result = evaluate_architecture(
        inventory("app.domain.order", "app.infrastructure.database"),
        (ImportEdge("app.domain.order", "app.infrastructure.database", 14, "runtime"),),
        ArchitectureConfig(
            layers=(
                ArchitectureLayer("domain", ("app.domain.**",)),
                ArchitectureLayer("infrastructure", ("app.infrastructure.**",)),
            ),
            forbidden=(ArchitectureForbidden("domain", "infrastructure"),),
        ),
    )

    assert result.violation_count == 1
    assert result.violations[0].line == 14
    assert result.violations[0].fingerprint == "forbidden: domain -> infrastructure|app.domain.order|app.infrastructure.database"


def test_reverse_forbidden_direction_is_allowed():
    result = evaluate_architecture(
        inventory("app.domain.order", "app.infrastructure.database"),
        (ImportEdge("app.infrastructure.database", "app.domain.order", 3, "runtime"),),
        ArchitectureConfig(
            layers=(
                ArchitectureLayer("domain", ("app.domain.**",)),
                ArchitectureLayer("infrastructure", ("app.infrastructure.**",)),
            ),
            forbidden=(ArchitectureForbidden("domain", "infrastructure"),),
        ),
    )

    assert result.violation_count == 0


def test_layered_architecture_allows_only_top_to_bottom():
    config = ArchitectureConfig(
        layers=tuple(ArchitectureLayer(name, (f"app.{name}.**",)) for name in ("api", "application", "domain")),
        layered=(ArchitectureLayered(("api", "application", "domain")),),
    )
    edges = (
        ImportEdge("app.api.http", "app.application.service", 1, "runtime"),
        ImportEdge("app.api.http", "app.domain.order", 2, "runtime"),
        ImportEdge("app.application.service", "app.domain.order", 3, "runtime"),
        ImportEdge("app.domain.order", "app.application.service", 4, "runtime"),
        ImportEdge("app.domain.order", "app.api.http", 5, "runtime"),
        ImportEdge("app.application.service", "app.api.http", 6, "runtime"),
    )

    result = evaluate_architecture(
        inventory("app.api.http", "app.application.service", "app.domain.order"), edges, config
    )

    assert {(item.source_module, item.target_module) for item in result.violations} == {
        ("app.application.service", "app.api.http"),
        ("app.domain.order", "app.api.http"),
        ("app.domain.order", "app.application.service"),
    }


def test_independent_modules_cannot_import_each_other():
    config = ArchitectureConfig(
        independent=(ArchitectureIndependent(("app.billing.**", "app.identity.**")),),
    )
    result = evaluate_architecture(
        inventory("app.billing.service", "app.identity.service"),
        (ImportEdge("app.billing.service", "app.identity.service", 8, "runtime"),),
        config,
    )

    assert result.violation_count == 1
    assert result.violations[0].source_layer == ""


def test_unmapped_module_is_allowed():
    config = ArchitectureConfig(
        layers=(ArchitectureLayer("domain", ("app.domain.**",)),),
        forbidden=(ArchitectureForbidden("domain", "domain"),),
    )

    result = evaluate_architecture(
        inventory("app.domain.order", "app.misc.tool"),
        (ImportEdge("app.domain.order", "app.misc.tool", 2, "runtime"),),
        config,
    )

    assert result.violation_count == 0


def test_overlapping_layer_patterns_are_a_config_error():
    config = ArchitectureConfig(
        layers=(
            ArchitectureLayer("one", ("app.**",)),
            ArchitectureLayer("two", ("app.domain.**",)),
        ),
    )

    with pytest.raises(ArchitectureConfigError):
        evaluate_architecture(inventory("app.domain.order"), (), config)


def test_type_checking_edge_is_not_a_violation():
    config = ArchitectureConfig(
        layers=(
            ArchitectureLayer("domain", ("app.domain.**",)),
            ArchitectureLayer("infrastructure", ("app.infrastructure.**",)),
        ),
        forbidden=(ArchitectureForbidden("domain", "infrastructure"),),
    )

    result = evaluate_architecture(
        inventory("app.domain.order", "app.infrastructure.database"),
        (ImportEdge("app.domain.order", "app.infrastructure.database", 9, "type_checking"),),
        config,
    )

    assert result.violation_count == 0


def test_fingerprint_does_not_change_when_line_moves():
    config = ArchitectureConfig(
        layers=(
            ArchitectureLayer("domain", ("app.domain.**",)),
            ArchitectureLayer("infrastructure", ("app.infrastructure.**",)),
        ),
        forbidden=(ArchitectureForbidden("domain", "infrastructure"),),
    )
    before = evaluate_architecture(
        inventory("app.domain.order", "app.infrastructure.database"),
        (ImportEdge("app.domain.order", "app.infrastructure.database", 9, "runtime"),),
        config,
    ).violations[0]
    after = evaluate_architecture(
        inventory("app.domain.order", "app.infrastructure.database"),
        (ImportEdge("app.domain.order", "app.infrastructure.database", 90, "runtime"),),
        config,
    ).violations[0]

    assert before.fingerprint == after.fingerprint


def test_architecture_config_is_explicit_and_parser_reads_contracts(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        """[tool.deslop.architecture]

[[tool.deslop.architecture.layers]]
name = "domain"
include = ["app.domain.**"]

[[tool.deslop.architecture.layers]]
name = "infrastructure"
include = ["app.infrastructure.**"]

[[tool.deslop.architecture.layers]]
name = "api"
include = ["app.api.**"]

[[tool.deslop.architecture.layers]]
name = "application"
include = ["app.application.**"]

[[tool.deslop.architecture.forbidden]]
from = "domain"
to = "infrastructure"

[[tool.deslop.architecture.independent]]
modules = ["app.billing.**", "app.identity.**"]

[[tool.deslop.architecture.layered]]
layers = ["api", "application", "domain"]
""",
        encoding="utf-8",
    )

    config = load_architecture_config(tmp_path)

    assert config.layers[0] == ArchitectureLayer("domain", ("app.domain.**",))
    assert config.forbidden[0] == ArchitectureForbidden("domain", "infrastructure")
    assert config.independent[0].patterns == ("app.billing.**", "app.identity.**")
    assert config.layered[0].layers == ("api", "application", "domain")


def test_architecture_policy_limits_are_loaded(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        """[tool.deslop.policy.architecture]
max-violations = 3
max-new-violations = 1
""",
        encoding="utf-8",
    )

    config = load_policy_config(tmp_path)

    assert config.max_architecture_violations == 3
    assert config.max_new_architecture_violations == 1


def test_audit_wires_architecture_to_existing_import_graph(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        """[tool.deslop]
source-roots = ["."]

[tool.deslop.architecture]
[[tool.deslop.architecture.layers]]
name = "domain"
include = ["app.domain.**"]
[[tool.deslop.architecture.layers]]
name = "infrastructure"
include = ["app.infrastructure.**"]
[[tool.deslop.architecture.forbidden]]
from = "domain"
to = "infrastructure"
""",
        encoding="utf-8",
    )
    (tmp_path / "app" / "domain").mkdir(parents=True)
    (tmp_path / "app" / "infrastructure").mkdir(parents=True)
    (tmp_path / "app" / "domain" / "order.py").write_text(
        "import app.infrastructure.database\n", encoding="utf-8"
    )
    (tmp_path / "app" / "infrastructure" / "database.py").write_text("value = 1\n", encoding="utf-8")

    result = analyze_project(tmp_path)

    assert result.architecture.violation_count == 1
    assert result.architecture.violations[0].source_module == "app.domain.order"


def test_policy_enforces_architecture_and_diff_counts_new_and_resolved():
    complete = DimensionCompleteness(AnalysisStatus.COMPLETE, ())
    score = SlopScore("test", 0.0, None, None, None, False)
    common = dict(
        inventory=SimpleNamespace(root="."),
        score=score,
        completeness=AuditCompleteness(complete, complete, complete),
        complexity=SimpleNamespace(files=(), eroded_function_count=0),
        duplication=SimpleNamespace(duplication_density=0.0),
        imports=SimpleNamespace(cycles=()),
        clone_groups=(),
    )
    base = SimpleNamespace(**common)
    base.architecture = evaluate_architecture(
        inventory("app.domain.order", "app.infrastructure.database"),
        (ImportEdge("app.domain.order", "app.infrastructure.database", 1, "runtime"),),
        ArchitectureConfig(
            layers=(ArchitectureLayer("domain", ("app.domain.**",)), ArchitectureLayer("infra", ("app.infrastructure.**",))),
            forbidden=(ArchitectureForbidden("domain", "infra"),),
        ),
    )
    current = SimpleNamespace(**common)
    current.architecture = evaluate_architecture(
        inventory("app.domain.order", "app.infrastructure.database", "app.api.http"),
        (
            ImportEdge("app.domain.order", "app.infrastructure.database", 2, "runtime"),
            ImportEdge("app.api.http", "app.infrastructure.database", 3, "runtime"),
        ),
        ArchitectureConfig(
            layers=(ArchitectureLayer("domain", ("app.domain.**",)), ArchitectureLayer("infra", ("app.infrastructure.**",)), ArchitectureLayer("api", ("app.api.**",))),
            forbidden=(ArchitectureForbidden("domain", "infra"), ArchitectureForbidden("api", "infra")),
        ),
    )

    difference = AuditDiff(base, current)

    assert difference.new_architecture_violations == 1
    assert difference.resolved_architecture_violations == 0
    assert not evaluate_diff(difference, PolicyConfig(max_new_architecture_violations=0)).passed
    assert not evaluate(base, PolicyConfig(max_architecture_violations=0)).passed

    resolved = SimpleNamespace(**common)
    resolved.architecture = base.architecture
    assert AuditDiff(current, resolved).resolved_architecture_violations == 1


def test_existing_architecture_violations_do_not_block_legacy_diff():
    complete = DimensionCompleteness(AnalysisStatus.COMPLETE, ())
    score = SlopScore("test", 0.0, None, None, None, False)
    common = dict(
        inventory=SimpleNamespace(root="."),
        score=score,
        completeness=AuditCompleteness(complete, complete, complete),
        complexity=SimpleNamespace(files=(), eroded_function_count=0),
        duplication=SimpleNamespace(duplication_density=0.0),
        imports=SimpleNamespace(cycles=()),
        clone_groups=(),
    )
    config = ArchitectureConfig(
        layers=(ArchitectureLayer("domain", ("app.domain.**",)), ArchitectureLayer("infra", ("app.infrastructure.**",))),
        forbidden=(ArchitectureForbidden("domain", "infra"),),
    )
    edge = ImportEdge("app.domain.order", "app.infrastructure.database", 1, "runtime")
    baseline = SimpleNamespace(**common, architecture=evaluate_architecture(inventory("app.domain.order", "app.infrastructure.database"), (edge,), config))
    current = SimpleNamespace(**common, architecture=evaluate_architecture(inventory("app.domain.order", "app.infrastructure.database"), (edge,), config))

    result = evaluate_diff(AuditDiff(baseline, current), PolicyConfig(max_new_architecture_violations=0))

    assert result.passed


def test_new_architecture_violation_blocks_legacy_diff():
    complete = DimensionCompleteness(AnalysisStatus.COMPLETE, ())
    score = SlopScore("test", 0.0, None, None, None, False)
    common = dict(
        inventory=SimpleNamespace(root="."),
        score=score,
        completeness=AuditCompleteness(complete, complete, complete),
        complexity=SimpleNamespace(files=(), eroded_function_count=0),
        duplication=SimpleNamespace(duplication_density=0.0),
        imports=SimpleNamespace(cycles=()),
        clone_groups=(),
    )
    baseline_config = ArchitectureConfig(
        layers=(ArchitectureLayer("domain", ("app.domain.**",)), ArchitectureLayer("infra", ("app.infrastructure.**",))),
        forbidden=(ArchitectureForbidden("domain", "infra"),),
    )
    current_config = ArchitectureConfig(
        layers=(
            ArchitectureLayer("domain", ("app.domain.**",)),
            ArchitectureLayer("infra", ("app.infrastructure.**",)),
            ArchitectureLayer("api", ("app.api.**",)),
        ),
        forbidden=(ArchitectureForbidden("domain", "infra"), ArchitectureForbidden("api", "infra")),
    )
    baseline_edge = ImportEdge("app.domain.order", "app.infrastructure.database", 1, "runtime")
    new_edge = ImportEdge("app.api.http", "app.infrastructure.database", 2, "runtime")
    baseline = SimpleNamespace(**common, architecture=evaluate_architecture(inventory("app.domain.order", "app.infrastructure.database"), (baseline_edge,), baseline_config))
    current = SimpleNamespace(**common, architecture=evaluate_architecture(inventory("app.domain.order", "app.infrastructure.database", "app.api.http"), (baseline_edge, new_edge), current_config))

    result = evaluate_diff(AuditDiff(baseline, current), PolicyConfig(max_new_architecture_violations=0))

    assert not result.passed
    assert "max-new-architecture-violations" in {item.rule for item in result.violations}
