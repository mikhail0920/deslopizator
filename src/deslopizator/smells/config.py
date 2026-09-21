from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 uses tomli
    import tomli as tomllib

from deslopizator.smells.models import SmellConfig


def _int(document: dict, key: str, default: int) -> int:
    value = document.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(document: dict, key: str, default: float) -> float:
    value = document.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_smell_config(root: Path | str) -> SmellConfig:
    path = Path(root)
    if path.is_file():
        path = path.parent
    config_path = path / "pyproject.toml"
    if not config_path.is_file():
        return SmellConfig()
    try:
        with config_path.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, ValueError):
        return SmellConfig()
    tool = document.get("tool", {})
    deslop = tool.get("deslop", {}) if isinstance(tool, dict) else {}
    raw = deslop.get("smells", {}) if isinstance(deslop, dict) else {}
    if not isinstance(raw, dict):
        return SmellConfig()
    return SmellConfig(
        version=str(raw.get("version", "1")),
        pass_through=bool(raw.get("pass-through", True)),
        delegation_chain=bool(raw.get("delegation-chain", True)),
        single_implementation_abstraction=bool(raw.get("single-implementation-abstraction", True)),
        swallowed_exception=bool(raw.get("swallowed-exception", True)),
        delegating_class=bool(raw.get("delegating-class", True)),
        delegating_class_min_methods=max(1, _int(raw, "delegating-class-min-methods", 3)),
        delegating_class_min_ratio=max(0.0, min(1.0, _float(raw, "delegating-class-min-ratio", 0.80))),
        delegation_chain_min_length=max(2, _int(raw, "delegation-chain-min-length", 3)),
    )
