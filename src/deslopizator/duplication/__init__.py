from deslopizator.duplication.detector import analyze_duplication, detect_clones
from deslopizator.duplication.models import CloneGroup, CloneInstance, DuplicationMetrics, NormalizedToken
from deslopizator.duplication.tokenizer import normalize_file, normalize_source

__all__ = [
    "CloneGroup",
    "CloneInstance",
    "DuplicationMetrics",
    "NormalizedToken",
    "analyze_duplication",
    "detect_clones",
    "normalize_file",
    "normalize_source",
]
