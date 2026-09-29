"""Text chunking strategies for the knowledge base (lesson 4).

Pure functions over text: they never touch the database, the embedding gateway
or the vector store, and they never modify the original knowledge_entries text
(callers pass a copy when preprocessing is requested). Offsets in custom mode
are relative to the PREPROCESSED text, per the course spec.

Strategies:
- auto:      ~800-char window, ~80-char overlap, break preferred at paragraph /
             line / sentence boundary; custom length params are ignored.
- custom:    100-2000 char window, 0%-50% overlap, optional URL/email stripping
             and whitespace collapsing; invalid params raise ChunkParamError.
- hierarchy: split on # / ## / ### headings (heading stays with its section),
             over-long sections are re-windowed with the auto rules.
"""
import re
from dataclasses import dataclass

AUTO_CHUNK_SIZE = 800
AUTO_CHUNK_OVERLAP = 80

CUSTOM_MIN_SIZE = 100
CUSTOM_MAX_SIZE = 2000

# Break separators in preference order; rfind keeps the latest of each kind.
_BREAK_SEPARATORS = ("\n\n", "\n", "。", "！", "？", ".", "!", "?")

_HEADING_RE = re.compile(r"^#{1,3}\s+.*$", re.MULTILINE)
_URL_RE = re.compile(r"https?://\S+")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_WHITESPACE_RE = re.compile(r"\s+")


class ChunkParamError(ValueError):
    """Raised when custom chunking parameters are outside allowed ranges."""


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    text: str
    char_start: int
    char_end: int


def preprocess(
    text: str,
    *,
    strip_urls: bool = False,
    strip_emails: bool = False,
    collapse_spaces: bool = False,
) -> str:
    """Return a preprocessed copy; the original text is untouched."""
    result = text
    if strip_urls:
        result = _URL_RE.sub(" ", result)
    if strip_emails:
        result = _EMAIL_RE.sub(" ", result)
    if collapse_spaces:
        result = _WHITESPACE_RE.sub(" ", result).strip()
    return result


def _find_break(text: str, start: int, hard_end: int) -> int:
    """Pick a friendly break in the SECOND HALF of the window.

    Breaks near the window start are ignored (they would peel off tiny chunks,
    e.g. an early heading line); falls back to the hard boundary otherwise.
    """
    window = text[start:hard_end]
    earliest = len(window) // 2
    for sep in _BREAK_SEPARATORS:
        pos = window.rfind(sep)
        if pos >= earliest:
            candidate = start + pos + len(sep)
            if start < candidate <= hard_end:
                return candidate
    return hard_end


def _window_chunks(
    text: str, size: int, overlap: int, base_offset: int = 0
) -> list[tuple[str, int, int]]:
    """Sliding window over text -> (chunk_text, abs_start, abs_end) tuples."""
    out: list[tuple[str, int, int]] = []
    n = len(text)
    start = 0
    while start < n:
        hard_end = min(start + size, n)
        if hard_end == n:
            end = n
        else:
            end = _find_break(text, start, hard_end)
        out.append((text[start:end], base_offset + start, base_offset + end))
        if end >= n:
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = start + 1
        start = next_start
    return out


def _auto_chunks(text: str) -> list[Chunk]:
    pieces = _window_chunks(text, AUTO_CHUNK_SIZE, AUTO_CHUNK_OVERLAP)
    return [
        Chunk(idx, piece_text, start, end)
        for idx, (piece_text, start, end) in enumerate(pieces)
    ]


def _custom_chunks(
    text: str,
    *,
    chunk_size: int,
    overlap_ratio: float,
    strip_urls: bool,
    strip_emails: bool,
    collapse_spaces: bool,
) -> list[Chunk]:
    if not isinstance(chunk_size, int) or not (CUSTOM_MIN_SIZE <= chunk_size <= CUSTOM_MAX_SIZE):
        raise ChunkParamError(
            f"chunk_size must be an integer within {CUSTOM_MIN_SIZE}-{CUSTOM_MAX_SIZE}"
        )
    if not (0.0 <= overlap_ratio <= 0.5):
        raise ChunkParamError("overlap_ratio must be within 0.0-0.5")

    prepared = preprocess(
        text,
        strip_urls=strip_urls,
        strip_emails=strip_emails,
        collapse_spaces=collapse_spaces,
    )
    overlap = int(chunk_size * overlap_ratio)
    pieces = _window_chunks(prepared, chunk_size, overlap)
    return [
        Chunk(idx, piece_text, start, end)
        for idx, (piece_text, start, end) in enumerate(pieces)
    ]


def _hierarchy_chunks(text: str) -> list[Chunk]:
    """Split by # / ## / ### headings; over-long sections re-window as auto."""
    boundaries = [0]
    for match in _HEADING_RE.finditer(text):
        if match.start() > 0:
            boundaries.append(match.start())
    boundaries.append(len(text))

    out: list[Chunk] = []
    for i in range(len(boundaries) - 1):
        sec_start, sec_end = boundaries[i], boundaries[i + 1]
        section = text[sec_start:sec_end]
        if not section.strip():
            continue
        if len(section) <= AUTO_CHUNK_SIZE:
            out.append(Chunk(len(out), section, sec_start, sec_end))
        else:
            for piece_text, start, end in _window_chunks(
                section, AUTO_CHUNK_SIZE, AUTO_CHUNK_OVERLAP, base_offset=sec_start
            ):
                out.append(Chunk(len(out), piece_text, start, end))
    return out


def chunk_text(
    text: str,
    strategy: str = "auto",
    *,
    chunk_size: int | None = None,
    overlap_ratio: float = 0.0,
    strip_urls: bool = False,
    strip_emails: bool = False,
    collapse_spaces: bool = False,
) -> list[Chunk]:
    """Chunk text with the chosen strategy.

    Returns an ordered list of Chunk(index, text, char_start, char_end).
    Empty/whitespace-only input yields an empty list.
    """
    if text is None or not text.strip():
        return []

    if strategy == "auto":
        return _auto_chunks(text)
    if strategy == "custom":
        if chunk_size is None:
            raise ChunkParamError("chunk_size is required for the custom strategy")
        return _custom_chunks(
            text,
            chunk_size=chunk_size,
            overlap_ratio=overlap_ratio,
            strip_urls=strip_urls,
            strip_emails=strip_emails,
            collapse_spaces=collapse_spaces,
        )
    if strategy == "hierarchy":
        return _hierarchy_chunks(text)
    raise ChunkParamError(
        f"unknown strategy '{strategy}' (expected auto|custom|hierarchy)"
    )
