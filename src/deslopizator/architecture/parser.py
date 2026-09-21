from __future__ import annotations

from pathlib import Path
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from deslopizator.architecture.models import (
    ArchitectureConfig,
    ArchitectureForbidden,
    ArchitectureIndependent,
    ArchitectureLayer,
    ArchitectureLayered,
)


class ArchitectureConfigError(ValueError):
    """Raised for malformed or internally inconsistent architecture config."""


def _strings(value, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ArchitectureConfigError(f"architecture {field} must be a list of non-empty strings")
    return tuple(value)


def _section(document: dict) -> dict:
    tool = document.get("tool", {})
    deslop = tool.get("deslop", {}) if isinstance(tool, dict) else {}
    architecture = deslop.get("architecture", {}) if isinstance(deslop, dict) else {}
    if architecture is None:
        return {}
    if not isinstance(architecture, dict):
        raise ArchitectureConfigError("tool.deslop.architecture must be a table")
    return architecture


def load_architecture_config(root: Path | str) -> ArchitectureConfig:
    path = Path(root)
    if path.is_file():
        path = path.parent
    config_path = path / "pyproject.toml"
    if not config_path.is_file():
        return ArchitectureConfig()
    with config_path.open("rb") as stream:
        document = tomllib.load(stream)
    architecture = _section(document)

    raw_layers = architecture.get("layers", [])
    if not isinstance(raw_layers, list):
        raise ArchitectureConfigError("architecture.layers must be an array of tables")
    layers = []
    for item in raw_layers:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"]:
            raise ArchitectureConfigError("each architecture layer needs a non-empty name")
        layers.append(ArchitectureLayer(item["name"], _strings(item.get("include", []), "layer include")))
    names = [layer.name for layer in layers]
    if len(names) != len(set(names)):
        raise ArchitectureConfigError("architecture layer names must be unique")

    raw_forbidden = architecture.get("forbidden", [])
    if not isinstance(raw_forbidden, list):
        raise ArchitectureConfigError("architecture.forbidden must be an array of tables")
    forbidden = []
    for item in raw_forbidden:
        if not isinstance(item, dict) or not isinstance(item.get("from"), str) or not isinstance(item.get("to"), str):
            raise ArchitectureConfigError("each forbidden rule needs from and to layers")
        forbidden.append(ArchitectureForbidden(item["from"], item["to"]))

    raw_independent = architecture.get("independent", [])
    if not isinstance(raw_independent, list):
        raise ArchitectureConfigError("architecture.independent must be an array of tables")
    independent = []
    for item in raw_independent:
        if not isinstance(item, dict):
            raise ArchitectureConfigError("each independent rule must be a table")
        independent.append(ArchitectureIndependent(_strings(item.get("modules", []), "independent modules")))

    raw_layered = architecture.get("layered", [])
    if not isinstance(raw_layered, list):
        raise ArchitectureConfigError("architecture.layered must be an array of tables")
    layered = []
    for item in raw_layered:
        if not isinstance(item, dict):
            raise ArchitectureConfigError("each layered rule must be a table")
        layered.append(ArchitectureLayered(_strings(item.get("layers", []), "layered layers")))

    known_names = set(names)
    for rule in (*forbidden, *layered):
        referenced = (rule.source_layer, rule.target_layer) if isinstance(rule, ArchitectureForbidden) else rule.layers
        unknown = set(referenced) - known_names
        if unknown:
            raise ArchitectureConfigError(f"architecture rule references unknown layer(s): {', '.join(sorted(unknown))}")
    return ArchitectureConfig(tuple(layers), tuple(forbidden), tuple(independent), tuple(layered))
