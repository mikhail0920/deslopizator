import io
import keyword
import re
import tokenize
from pathlib import Path

from deslopizator.duplication.models import NormalizedToken


_IGNORED_TOKEN_TYPES = {
    tokenize.COMMENT,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.ENCODING,
    tokenize.ENDMARKER,
}
_STRING_PREFIX = re.compile(r"(?i)^(?:[rubf]|br|rb|fr|rf)+")


def _normalize_token(token: tokenize.TokenInfo) -> str | None:
    if token.type in _IGNORED_TOKEN_TYPES:
        return None
    if token.type == tokenize.NAME:
        if keyword.iskeyword(token.string) or keyword.issoftkeyword(token.string):
            return token.string
        return "NAME"
    if token.type == tokenize.STRING:
        prefix = _STRING_PREFIX.match(token.string)
        if prefix and "b" in prefix.group(0).lower():
            return "BYTES"
        return "STRING"
    if token.type == tokenize.NUMBER:
        return "NUMBER"
    if token.type == tokenize.INDENT:
        return "INDENT"
    if token.type == tokenize.DEDENT:
        return "DEDENT"
    return token.string


def normalize_source(source: str) -> tuple[NormalizedToken, ...]:
    normalized: list[NormalizedToken] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        value = _normalize_token(token)
        if value is not None:
            normalized.append(NormalizedToken(value, token.start[0], token.start[1]))
    return tuple(normalized)


def normalize_file(path: Path) -> tuple[NormalizedToken, ...]:
    return normalize_source(path.read_text(encoding="utf-8"))


def production_sloc(source: str) -> int:
    lines: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in _IGNORED_TOKEN_TYPES | {tokenize.INDENT, tokenize.DEDENT}:
            continue
        lines.update(range(token.start[0], token.end[0] + 1))
    return len(lines)
