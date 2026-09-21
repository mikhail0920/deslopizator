from deslopizator.duplication.detector import analyze_duplication, analyze_duplication_facts, detect_clones
from deslopizator.duplication.models import CloneGroup, CloneInstance, DuplicationMetrics, NormalizedToken
from deslopizator.duplication.tokenizer import normalize_file, normalize_source

__all__ = [
    "CloneGroup",
    "CloneInstance",
    "DuplicationMetrics",
    "NormalizedToken",
    "analyze_duplication",
    "analyze_duplication_facts",
    "detect_clones",
    "normalize_file",
    "normalize_source",
]
