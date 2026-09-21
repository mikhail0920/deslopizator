from pathlib import Path

from deslopizator.audit import analyze_project
from deslopizator.cli import audit
from deslopizator.policy import AuditDiff, PolicyConfig, evaluate_diff
from deslopizator.snapshots import read_snapshot, write_snapshot


def project(root: Path, source: str, config: str = "") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text(source, encoding="utf-8")
    if config:
        (root / "pyproject.toml").write_text(config, encoding="utf-8")
    return root


def test_pass_through_and_exemptions(tmp_path):
    result = analyze_project(project(tmp_path, """
def wrapper(value):
    return service.get(value)

@property
def property_wrapper(value):
    return service.get(value)

def __dunder__(value):
    return service.get(value)
"""))
    assert [item.rule for item in result.smells.findings] == ["pass-through"]


def test_delegating_class_and_exception_findings(tmp_path):
    result = analyze_project(project(tmp_path, """
class Service:
    def get(self, value):
        return self.repo.get(value)
    def save(self, value):
        return self.repo.save(value)
    def delete(self, value):
        return self.repo.delete(value)

def read(value):
    try:
        return load(value)
    except Exception:
        return []
"""))
    rules = {item.rule for item in result.smells.findings}
    assert {"pass-through", "delegating-class", "swallowed-exception"} <= rules


def test_single_implementation_abstraction_is_medium(tmp_path):
    result = analyze_project(project(tmp_path, """
from abc import ABC, abstractmethod

class Store(ABC):
    @abstractmethod
    def get(self, key): ...

class MemoryStore(Store):
    def get(self, key):
        return key
"""))
    finding = next(item for item in result.smells.findings if item.rule == "single-implementation-abstraction")
    assert finding.confidence == "medium"
    assert finding.facts["implementations"] == ("MemoryStore",)


def test_suppression_is_reported_but_not_emitted(tmp_path):
    result = analyze_project(project(tmp_path, """
# deslop: ignore[pass-through]
def wrapper(value):
    return service.get(value)
"""))
    assert result.smells.findings == ()
    assert result.smells.suppressed_findings == 1


def test_file_suppression(tmp_path):
    result = analyze_project(project(tmp_path, """
# deslop: ignore-file[pass-through]
def wrapper(value):
    return service.get(value)
"""))
    assert result.smells.findings == ()
    assert result.smells.suppressed_findings == 1


def test_config_can_disable_smells(tmp_path):
    result = analyze_project(project(tmp_path, "def wrapper(value):\n    return service.get(value)\n", """[tool.deslop.smells]
pass-through = false
"""))
    assert result.smells.findings == ()


def test_delegation_chain_is_reported_when_class_assignments_resolve(tmp_path):
    result = analyze_project(project(tmp_path, """
class Repository:
    def run(self, value):
        return value

class Manager:
    def __init__(self):
        self.repo = Repository()
    def run(self, value):
        return self.repo.run(value)

class Service:
    def __init__(self):
        self.manager = Manager()
    def run(self, value):
        return self.manager.run(value)

class Controller:
    def __init__(self):
        self.service = Service()
    def run(self, value):
        return self.service.run(value)
"""))
    chains = [item for item in result.smells.findings if item.rule == "delegation-chain"]
    assert chains
    assert max(item.facts["length"] for item in chains) >= 3


def test_smell_fingerprint_survives_line_shift_and_diff_tracks_new_resolved(tmp_path):
    before = analyze_project(project(tmp_path / "before", "def wrapper(value):\n    return service.get(value)\n"))
    after = analyze_project(project(tmp_path / "after", "# header\n\ndef wrapper(value):\n    return service.get(value)\n"))
    assert AuditDiff(before, after).new_slop == ()
    changed = analyze_project(project(tmp_path / "changed", "x = 1\n"))
    assert len(AuditDiff(before, changed).resolved_slop) == 1
    assert len(AuditDiff(changed, after).new_slop) == 1


def test_smell_policy_blocks_new_high(tmp_path):
    before = analyze_project(project(tmp_path / "before", "x = 1\n"))
    after = analyze_project(project(tmp_path / "after", "def wrapper(value):\n    return service.get(value)\n"))
    policy = evaluate_diff(AuditDiff(before, after), PolicyConfig(max_new_high_smells=0))
    assert not policy.passed
    assert "max-new-high-smells" in {item.rule for item in policy.violations}


def test_smells_are_advisory_and_do_not_change_structural_score(tmp_path):
    before = analyze_project(project(tmp_path / "before", "x = 1\n"))
    after = analyze_project(project(tmp_path / "after", "def wrapper(value):\n    return service.get(value)\n"))
    assert after.smells.findings
    assert after.score == before.score


def test_smell_snapshot_roundtrip_and_determinism(tmp_path):
    result = analyze_project(project(tmp_path / "project", "def wrapper(value):\n    return service.get(value)\n"))
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    write_snapshot(result, first)
    loaded = read_snapshot(first)
    write_snapshot(loaded, second)
    assert first.read_bytes() == second.read_bytes()
    assert loaded.smells == result.smells


def test_cli_sarif_format(tmp_path, capsys):
    root = project(tmp_path, "def wrapper(value):\n    return service.get(value)\n")
    assert audit(root, output_format="sarif") == 0
    assert '"runs"' in capsys.readouterr().out
