from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
from pathlib import Path

from deslopizator.duplication.models import CloneGroup, CloneInstance, DuplicationMetrics, NormalizedToken
from deslopizator.duplication.tokenizer import normalize_file, production_sloc


@dataclass(frozen=True)
class _TokenFile:
    path: Path
    tokens: tuple[NormalizedToken, ...]
    production_sloc: int


@dataclass(frozen=True)
class _Candidate:
    token_count: int
    occurrences: tuple[tuple[int, int, int], ...]


def _window_hash(tokens: tuple[NormalizedToken, ...], start: int, size: int) -> bytes:
    payload = "\x1f".join(token.value for token in tokens[start : start + size]).encode("utf-8")
    return sha256(payload).digest()


def _same_window(left: tuple[NormalizedToken, ...], left_start: int, right: tuple[NormalizedToken, ...], right_start: int, size: int) -> bool:
    return tuple(token.value for token in left[left_start : left_start + size]) == tuple(token.value for token in right[right_start : right_start + size])


def _same_file_ranges_overlap(left_start: int, left_end: int, right_start: int, right_end: int) -> bool:
    return max(left_start, right_start) <= min(left_end, right_end)


def _extend_match(left: _TokenFile, left_start: int, right: _TokenFile, right_start: int, minimum: int) -> tuple[int, int, int, int]:
    left_end = left_start + minimum
    right_end = right_start + minimum
    while left_end < len(left.tokens) and right_end < len(right.tokens) and left.tokens[left_end].value == right.tokens[right_end].value:
        left_end += 1
        right_end += 1
    while left_start > 0 and right_start > 0 and left.tokens[left_start - 1].value == right.tokens[right_start - 1].value:
        left_start -= 1
        right_start -= 1
    return left_start, left_end, right_start, right_end


def _candidate_is_valid(left: _TokenFile, left_start: int, left_end: int, right: _TokenFile, right_start: int, right_end: int) -> bool:
    if left.path != right.path:
        return True
    return not _same_file_ranges_overlap(left_start, left_end - 1, right_start, right_end - 1)


def _collect_candidates(files: list[_TokenFile], minimum: int) -> list[_Candidate]:
    windows: dict[bytes, list[tuple[int, int]]] = defaultdict(list)
    for file_index, token_file in enumerate(files):
        for start in range(0, len(token_file.tokens) - minimum + 1):
            windows[_window_hash(token_file.tokens, start, minimum)].append((file_index, start))

    candidates: list[_Candidate] = []
    for occurrences in windows.values():
        if len(occurrences) < 2:
            continue
        for (left_index, left_start), (right_index, right_start) in combinations(occurrences, 2):
            left = files[left_index]
            right = files[right_index]
            if left_index == right_index and left_start == right_start:
                continue
            if not _same_window(left.tokens, left_start, right.tokens, right_start, minimum):
                continue
            left_start, left_end, right_start, right_end = _extend_match(left, left_start, right, right_start, minimum)
            if not _candidate_is_valid(left, left_start, left_end, right, right_start, right_end):
                continue
            candidates.append(
                _Candidate(
                    left_end - left_start,
                    ((left_index, left_start, left_end), (right_index, right_start, right_end)),
                )
            )
    return candidates


def _occurrence_is_contained(candidate: tuple[int, int, int], selected: tuple[int, int, int], files: list[_TokenFile], candidate_count: int) -> bool:
    candidate_file, candidate_start, candidate_end = candidate
    selected_file, selected_start, selected_end = selected
    if candidate_file != selected_file or candidate_start < selected_start or candidate_end > selected_end:
        return False
    candidate_values = tuple(token.value for token in files[candidate_file].tokens[candidate_start:candidate_end])
    selected_values = tuple(token.value for token in files[selected_file].tokens[selected_start:selected_end])
    offset = candidate_start - selected_start
    return len(candidate_values) == candidate_count and candidate_values == selected_values[offset : offset + candidate_count]


def _merge_candidates(candidates: list[_Candidate], files: list[_TokenFile]) -> list[CloneGroup]:
    selected: list[tuple[int, list[tuple[int, int, int]]]] = []
    for candidate in sorted(candidates, key=lambda item: (-item.token_count, item.occurrences)):
        existing = None
        for token_count, occurrences in selected:
            if token_count != candidate.token_count:
                continue
            if any(_occurrence_is_contained(item, selected_item, files, candidate.token_count) for item in candidate.occurrences for selected_item in occurrences):
                existing = occurrences
                break
        if existing is not None:
            for occurrence in candidate.occurrences:
                if occurrence in existing:
                    continue
                if any(
                    occurrence[0] == selected_item[0]
                    and max(occurrence[1], selected_item[1]) < min(occurrence[2], selected_item[2])
                    for selected_item in existing
                ):
                    continue
                if not any(_occurrence_is_contained(occurrence, selected_item, files, candidate.token_count) for selected_item in existing):
                    existing.append(occurrence)
            continue

        covered = False
        for token_count, occurrences in selected:
            if token_count >= candidate.token_count and all(any(_occurrence_is_contained(item, selected_item, files, candidate.token_count) for selected_item in occurrences) for item in candidate.occurrences):
                covered = True
                break
        if not covered:
            selected.append((candidate.token_count, list(candidate.occurrences)))

    groups: list[CloneGroup] = []
    for token_count, occurrences in selected:
        instances = []
        for file_index, start, end in occurrences:
            tokens = files[file_index].tokens
            end_token = next(token for token in reversed(tokens[start:end]) if token.value not in {"INDENT", "DEDENT"})
            instances.append(CloneInstance(str(files[file_index].path), tokens[start].line, end_token.line))
        groups.append(CloneGroup(token_count, tuple(sorted(set(instances), key=lambda item: (item.path, item.start_line, item.end_line)))))
    return sorted(
        groups,
        key=lambda group: (
            group.instances[0].path,
            group.instances[0].start_line,
            group.instances[0].end_line,
            -group.token_count,
        ),
    )


def detect_clones(paths: list[Path | str], minimum_tokens: int = 100) -> tuple[CloneGroup, ...]:
    normalized_paths = sorted((Path(path) for path in paths), key=str)
    files = [_TokenFile(path, normalize_file(path), production_sloc(path.read_text(encoding="utf-8"))) for path in normalized_paths]
    return tuple(_merge_candidates(_collect_candidates(files, minimum_tokens), files))


def _duplicated_lines(groups: tuple[CloneGroup, ...]) -> int:
    lines_by_path: dict[str, set[int]] = defaultdict(set)
    for group in groups:
        for instance in group.instances:
            lines_by_path[instance.path].update(range(instance.start_line, instance.end_line + 1))
    return sum(len(lines) for lines in lines_by_path.values())


def analyze_duplication(paths: list[Path | str], minimum_tokens: int = 100) -> tuple[tuple[CloneGroup, ...], DuplicationMetrics]:
    normalized_paths = [Path(path) for path in paths]
    groups = detect_clones(normalized_paths, minimum_tokens)
    production_lines = sum(production_sloc(path.read_text(encoding="utf-8")) for path in normalized_paths)
    duplicated_lines = _duplicated_lines(groups)
    density = duplicated_lines / production_lines if production_lines else 0.0
    metrics = DuplicationMetrics(
        clone_group_count=len(groups),
        clone_instance_count=sum(len(group.instances) for group in groups),
        duplicated_lines=duplicated_lines,
        production_sloc=production_lines,
        duplication_density=density,
    )
    return groups, metrics
