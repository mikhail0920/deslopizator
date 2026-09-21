"""Versioned, portable JSON audit snapshots (no absolute checkout paths)."""
import json
from dataclasses import asdict
from enum import Enum
from pathlib import Path

from deslopizator.completeness.models import AnalysisStatus, AuditCompleteness, AuditResult, DimensionCompleteness
from deslopizator.duplication.models import CloneGroup, CloneInstance, DuplicationMetrics
from deslopizator.imports.models import ImportCycle, ImportMetrics
from deslopizator.inventory.models import FileKind, ProjectInventory, SourceFile
from deslopizator.models import ComplexityMetrics, FileComplexityMetrics, FunctionMetrics
from deslopizator.scoring.models import DimensionScore, SlopScore
from deslopizator.history.models import ChangeCoupling, FileChurn, FileStructuralDebt, Hotspot

SCHEMA_VERSION = 1


def write_snapshot(result: AuditResult, path: Path) -> None:
    root = result.inventory.root

    def portable(value):
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, str):
            if value == root:
                return "."
            return value.replace(root + "\\", "").replace(root + "/", "").replace("\\", "/")
        if isinstance(value, dict):
            return {key: portable(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [portable(item) for item in value]
        return value

    document = {"schema_version": SCHEMA_VERSION, "audit": portable(asdict(result))}
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def read_snapshot(path: Path) -> AuditResult:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported snapshot schema version")
    data = document["audit"]
    inventory = data["inventory"]
    inventory = ProjectInventory(inventory["root"], tuple(
        SourceFile(file["path"], file["module"], FileKind(file["kind"])) for file in inventory["files"]
    ), tuple(inventory["source_roots"]))
    complexity = dict(data["complexity"])
    complexity["files"] = tuple(
        FileComplexityMetrics(**{**file, "functions": tuple(FunctionMetrics(**function) for function in file["functions"])})
        for file in complexity["files"]
    )
    imports = dict(data["imports"])
    imports["cycles"] = tuple(ImportCycle(tuple(cycle["modules"])) for cycle in imports["cycles"])
    completeness = AuditCompleteness(**{
        name: DimensionCompleteness(AnalysisStatus(value["status"]), tuple(value["reasons"]))
        for name, value in data["completeness"].items()
    })
    score = dict(data["score"])
    for name in ("complexity", "duplication", "cycles"):
        if score[name] is not None:
            score[name] = DimensionScore(**score[name])
    groups = tuple(CloneGroup(group["token_count"], tuple(CloneInstance(**item) for item in group["instances"]), group["fingerprint"]) for group in data["clone_groups"])
    churn = tuple(FileChurn(**item) for item in data.get("churn", ()))
    structural_debt = tuple(FileStructuralDebt(**item) for item in data.get("structural_debt", ()))
    hotspots = tuple(Hotspot(**item) for item in data.get("hotspots", ()))
    coupling = tuple(ChangeCoupling(**item) for item in data.get("coupling", ()))
    return AuditResult(
        inventory,
        ComplexityMetrics(**complexity),
        DuplicationMetrics(**data["duplication"]),
        ImportMetrics(**imports),
        completeness,
        SlopScore(**score),
        groups,
        churn,
        structural_debt,
        hotspots,
        data.get("git_available", False),
        tuple(data.get("history_reasons", ())),
        coupling,
        data.get("coupling_available", False),
        tuple(data.get("coupling_reasons", ())),
    )
