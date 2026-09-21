from types import SimpleNamespace
import pytest
from deslopizator import cli
from deslopizator.completeness import AnalysisStatus, AuditCompleteness, DimensionCompleteness
from deslopizator.policy import AuditDiff, PolicyConfig, evaluate, evaluate_diff

def audit(*, score=20.0, eroded=0, density=0.0, clones=0, cycles=0, partial=False):
    status = AnalysisStatus.PARTIAL if partial else AnalysisStatus.COMPLETE
    dimension = DimensionCompleteness(status, ("unresolved local import",) if partial else ())
    return SimpleNamespace(inventory=SimpleNamespace(root="."), clone_groups=tuple(SimpleNamespace(fingerprint=str(i)) for i in range(clones)), score=SimpleNamespace(total=score, version="test"), complexity=SimpleNamespace(eroded_function_count=eroded, files=(SimpleNamespace(path="app.py", functions=tuple(SimpleNamespace(qualified_name=f"f{i}", eroded=True) for i in range(eroded))),)), duplication=SimpleNamespace(duplication_density=density, clone_group_count=clones), imports=SimpleNamespace(cycle_group_count=cycles, cycles=tuple(SimpleNamespace(modules=(f"a{i}", f"b{i}")) for i in range(cycles))), completeness=AuditCompleteness(dimension, dimension, dimension))

def test_old_high_score_does_not_fail_diff_policy():
    assert evaluate_diff(AuditDiff(audit(score=62), audit(score=61)), PolicyConfig(max_score_increase=0)).passed

def test_score_increase_fails_policy():
    result = evaluate_diff(AuditDiff(audit(score=62), audit(score=63)), PolicyConfig(max_score_increase=0))
    assert not result.passed and result.violations[0].rule == "max-score-increase"

def test_improvement_passes_regression_policy():
    result = evaluate_diff(AuditDiff(audit(score=62, density=.2, clones=3, cycles=2), audit(score=50, density=.1, clones=1, cycles=1)), PolicyConfig(max_score_increase=0))
    assert result.passed

@pytest.mark.parametrize(("field", "rule"), [("eroded", "max-new-eroded-functions"), ("clones", "max-new-clone-groups"), ("cycles", "max-new-cycle-groups")])
def test_new_budget_items_fail(field, rule):
    result = evaluate_diff(AuditDiff(audit(), audit(**{field: 1})), PolicyConfig())
    assert not result.passed and rule in {item.rule for item in result.violations}

def test_new_duplication_density_fails_budget():
    result = evaluate_diff(AuditDiff(audit(density=.1), audit(density=.12)), PolicyConfig())
    assert not result.passed and "max-density-increase" in {item.rule for item in result.violations}

def test_resolved_clone_does_not_fail():
    assert evaluate_diff(AuditDiff(audit(clones=2), audit(clones=0)), PolicyConfig()).passed

def test_partial_analysis_fails_by_default_and_can_be_allowed():
    diff = AuditDiff(audit(partial=True), audit(partial=True))
    assert not evaluate_diff(diff, PolicyConfig()).passed
    assert evaluate_diff(diff, PolicyConfig(allow_partial=True)).passed

def test_max_score_is_standalone_policy():
    result = evaluate(audit(score=36), PolicyConfig(max_score=35))
    assert not result.passed and result.violations[0].rule == "max-score"

def test_policy_config_is_loaded_from_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("""[tool.deslop.policy]
max-score = 40
max-score-increase = 0
allow-partial = true
[tool.deslop.policy.complexity]
max-new-eroded-functions = 2
[tool.deslop.policy.duplication]
max-density-increase = 0.02
max-new-clone-groups = 3
[tool.deslop.policy.cycles]
max-new-cycle-groups = 4
""", encoding="utf-8")
    from deslopizator.policy import load_policy_config
    assert load_policy_config(tmp_path) == PolicyConfig(40, 0, 2, .02, 3, 4, True)

def test_check_exit_codes(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "analyze_project", lambda path: audit(score=36))
    (tmp_path / "pyproject.toml").write_text("[tool.deslop.policy]\nmax-score = 35\n", encoding="utf-8")
    assert cli.check(tmp_path, None) == 1
    monkeypatch.setattr(cli, "analyze_project", lambda path: (_ for _ in ()).throw(RuntimeError("broken")))
    assert cli.check(tmp_path, None) == 2
