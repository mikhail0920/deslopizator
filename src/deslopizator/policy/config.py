from dataclasses import dataclass
from pathlib import Path
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

@dataclass(frozen=True)
class PolicyConfig:
    max_score: float | None = 35.0
    max_score_increase: float = 1.0
    max_new_eroded_functions: int = 0
    max_density_increase: float = 0.01
    max_new_clone_groups: int = 0
    max_new_cycle_groups: int = 0
    allow_partial: bool = False
    max_architecture_violations: int = 0
    max_new_architecture_violations: int = 0
    max_new_certain_smells: int = 0
    max_new_high_smells: int = 0

def _number(document: dict, key: str, default, cast):
    try:
        return cast(document.get(key, default))
    except (TypeError, ValueError):
        return default

def load_policy_config(root: Path | str) -> PolicyConfig:
    path = Path(root)
    if path.is_file():
        path = path.parent
    config_path = path / "pyproject.toml"
    if not config_path.is_file():
        return PolicyConfig()
    with config_path.open("rb") as stream:
        document = tomllib.load(stream)
    tool = document.get("tool", {})
    deslop = tool.get("deslop", {}) if isinstance(tool, dict) else {}
    policy = deslop.get("policy", {}) if isinstance(deslop, dict) else {}
    if not isinstance(policy, dict):
        return PolicyConfig()
    complexity = policy.get("complexity", {})
    duplication = policy.get("duplication", {})
    cycles = policy.get("cycles", {})
    architecture = policy.get("architecture", {})
    smells = policy.get("smells", {})
    complexity = complexity if isinstance(complexity, dict) else {}
    duplication = duplication if isinstance(duplication, dict) else {}
    cycles = cycles if isinstance(cycles, dict) else {}
    architecture = architecture if isinstance(architecture, dict) else {}
    smells = smells if isinstance(smells, dict) else {}
    raw_max = policy.get("max-score", 35.0)
    max_score = None if raw_max is None else _number({"value": raw_max}, "value", 35.0, float)
    return PolicyConfig(
        max_score=max_score,
        max_score_increase=_number(policy, "max-score-increase", 1.0, float),
        max_new_eroded_functions=_number(complexity, "max-new-eroded-functions", 0, int),
        max_density_increase=_number(duplication, "max-density-increase", 0.01, float),
        max_new_clone_groups=_number(duplication, "max-new-clone-groups", 0, int),
        max_new_cycle_groups=_number(cycles, "max-new-cycle-groups", 0, int),
        allow_partial=bool(policy.get("allow-partial", False)),
        max_architecture_violations=_number(architecture, "max-violations", 0, int),
        max_new_architecture_violations=_number(architecture, "max-new-violations", 0, int),
        max_new_certain_smells=_number(smells, "max-new-certain", 0, int),
        max_new_high_smells=_number(smells, "max-new-high", 0, int),
    )
