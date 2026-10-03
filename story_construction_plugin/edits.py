"""Pure text edits for chapter proposals: apply, check, preview.

The Agent never writes a chapter. It proposes a list of edits; this module
applies them to a base text in memory, flags text that is not story body, and
builds the before/after view the Desktop shows. Nothing here touches a file.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MAX_EDITS = 50
MAX_TEXT_CHARS = 200_000
_OPS = ("replace", "insert_after", "insert_before", "append", "prepend", "rewrite")
_FIELDS = {
    "replace": ("old_text", "new_text"),
    "insert_after": ("anchor_text", "new_text"),
    "insert_before": ("anchor_text", "new_text"),
    "append": ("new_text",),
    "prepend": ("new_text",),
    "rewrite": ("content",),
}
# Both sides must be non-empty except the replacement of a replace, which may delete.
_ALLOW_EMPTY = {("replace", "new_text")}
# A char-level diff is quadratic; past this size the preview falls back to whole paragraphs.
_INLINE_LIMIT = 4_000_000


class EditError(ValueError):
    """An edit list that cannot be applied; ``code`` is stable for tool callers."""

    def __init__(self, code: str, message: str, *, index: int | None = None, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.index = index
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": str(self)}
        if self.index is not None:
            payload["edit"] = self.index
        payload.update(self.details)
        return payload


@dataclass(frozen=True, slots=True)
class Edit:
    op: str
    old_text: str = ""
    new_text: str = ""
    anchor_text: str = ""
    content: str = ""

    def as_dict(self) -> dict[str, str]:
        fields = {name: getattr(self, name) for name in _FIELDS[self.op]}
        return {"op": self.op, **fields}


@dataclass(frozen=True, slots=True)
class BodyWarning:
    edit: int
    kind: str
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {"edit": self.edit, "kind": self.kind, "text": self.text}


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def text_digest(text: str) -> str:
    return hashlib.sha256(normalize_newlines(text).encode("utf-8")).hexdigest()


def edits_digest(edits: Iterable[Edit]) -> str:
    payload = json.dumps([edit.as_dict() for edit in edits], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_edits(raw: object) -> tuple[Edit, ...]:
    """Validate the Agent's edit list and return normalized edits."""

    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or not raw:
        raise EditError("edits_required", "edits must be a non-empty list")
    if len(raw) > MAX_EDITS:
        raise EditError("too_many_edits", f"at most {MAX_EDITS} edits per proposal")
    edits: list[Edit] = []
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise EditError("invalid_edit", "each edit must be an object", index=index)
        op = row.get("op")
        if op not in _OPS:
            raise EditError("invalid_edit", f"op must be one of {', '.join(_OPS)}", index=index)
        values: dict[str, str] = {}
        for name in _FIELDS[op]:
            value = row.get(name)
            if not isinstance(value, str):
                raise EditError("invalid_edit", f"{name} must be a string", index=index)
            value = normalize_newlines(value)
            if not value and (op, name) not in _ALLOW_EMPTY:
                raise EditError("invalid_edit", f"{name} must not be empty", index=index)
            if len(value) > MAX_TEXT_CHARS:
                raise EditError("text_too_long", f"{name} is too long", index=index)
            values[name] = value
        edits.append(Edit(op=op, **values))
    if any(edit.op == "rewrite" for edit in edits) and len(edits) != 1:
        raise EditError("rewrite_must_be_alone", "a rewrite cannot be combined with other edits")
    return tuple(edits)


def apply_edits(base_text: str, edits: Sequence[Edit]) -> str:
    """Apply edits in order; each one sees the result of the previous one."""

    text = normalize_newlines(base_text)
    for index, edit in enumerate(edits):
        text = _apply_one(text, edit, index)
        if len(text) > MAX_TEXT_CHARS * 2:
            raise EditError("text_too_long", "the result is too long", index=index)
    return text


def _apply_one(text: str, edit: Edit, index: int) -> str:
    if edit.op == "rewrite":
        return edit.content
    if edit.op == "append":
        return _join(text, edit.new_text, after=True)
    if edit.op == "prepend":
        return _join(text, edit.new_text, after=False)
    needle = edit.old_text if edit.op == "replace" else edit.anchor_text
    start, end = _locate(text, needle, index)
    if edit.op == "replace":
        return text[:start] + edit.new_text + text[end:]
    if edit.op == "insert_after":
        return text[:end] + edit.new_text + text[end:]
    return text[:start] + edit.new_text + text[start:]


def _locate(text: str, needle: str, index: int) -> tuple[int, int]:
    """The one span of ``text`` the edit points at; an exact match wins."""

    found = text.count(needle)
    if found == 1:
        start = text.index(needle)
        return start, start + len(needle)
    if found > 1:
        raise _ambiguous(index, found)
    # No exact match: tolerate what a model routinely gets wrong when it copies
    # text (curly vs straight quotes, dash and space variants, trailing blanks).
    folded_text, positions = _fold(text)
    folded_needle, _ = _fold(needle)
    if folded_needle.strip():
        matches = _find_all(folded_text, folded_needle)
        if len(matches) > 1:
            raise _ambiguous(index, len(matches))
        if matches:
            first = matches[0]
            return positions[first], positions[first + len(folded_needle) - 1] + 1
    raise EditError(
        "edit_not_found",
        "the text to locate does not appear in the text; read it again and copy it exactly",
        index=index,
    )


def _ambiguous(index: int, matches: int) -> EditError:
    return EditError(
        "edit_ambiguous",
        f"the text to locate appears {matches} times; include more surrounding text so it appears once",
        index=index,
        matches=matches,
    )


# Characters that only differ in typography. Folding maps one character to one
# character, so a position in the folded text is a position in the original.
_FOLD = {
    **dict.fromkeys("\u2018\u2019\u201a\u201b", "'"),
    **dict.fromkeys("\u201c\u201d\u201e\u201f", '"'),
    **dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212", "-"),
    **dict.fromkeys(
        "\u00a0\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000", " "
    ),
}
# NFKC is deliberately not used: it would turn full-width CJK punctuation into
# half-width and stop a quoted sentence from matching its own source.


def _fold(text: str) -> tuple[str, list[int]]:
    """Typography-folded text with trailing blanks removed from every line, plus
    the original position of each kept character."""

    out: list[str] = []
    positions: list[int] = []
    offset = 0
    lines = text.split("\n")
    for number, line in enumerate(lines):
        kept = line.rstrip(" \t　 ")
        for column, char in enumerate(kept):
            out.append(_FOLD.get(char, char))
            positions.append(offset + column)
        if number < len(lines) - 1:
            out.append("\n")
            positions.append(offset + len(line))
        offset += len(line) + 1
    return "".join(out), positions


def _find_all(haystack: str, needle: str) -> list[int]:
    """Start offsets of every non-overlapping occurrence of ``needle``."""

    found: list[int] = []
    start = haystack.find(needle)
    while start != -1:
        found.append(start)
        start = haystack.find(needle, start + len(needle))
    return found


def _join(text: str, addition: str, *, after: bool) -> str:
    if not text.strip():
        return addition
    if after:
        return text.rstrip("\n") + "\n\n" + addition.lstrip("\n")
    return addition.rstrip("\n") + "\n\n" + text.lstrip("\n")


# --------------------------------------------------------------- body checks
_LEAD_IN = re.compile(
    r"^\s*(?:"
    r"(?:好的|当然|没问题|收到|明白了?|了解|可以)[，,。.！!：:\s]"
    r"|以下是|下面是|以下为|如下[：:]"
    r"|我(?:已经|已|来|将|会|为你|帮你)[^\n]{0,24}(?:修改|改写|重写|润色|生成|写了|写好)"
    r"|(?:sure|certainly|of course|okay|ok)\b[,.!:\s]"
    r"|here(?:'s| is| are)\b"
    r"|below is\b"
    r")",
    re.IGNORECASE,
)
_TRAILING = re.compile(
    r"^\s*(?:"
    r"希望(?:这|以上|能|对你|你)"
    r"|如(?:果)?(?:你)?(?:还)?(?:需要?|有需要|想要?|有其他|有任何)"
    r"|需要我|要不要我|如有(?:其他|任何|需要)"
    r"|让我知道|请告诉我|以上(?:是|就是|为)"
    r"|let me know\b|i hope this\b|hope this\b|feel free\b|if you(?:'d| would)? like\b"
    r")",
    re.IGNORECASE,
)
_FENCE = re.compile(r"\A\s*```[^\n]*\n(?P<body>.*?)\n?```\s*\Z", re.DOTALL)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(?P<title>.+?)\s*#*\s*$")


def clean_body(text: str, *, index: int = 0, title: str | None = None) -> tuple[str, list[BodyWarning]]:
    """Strip a wrapping code fence, reject frontmatter and flag guidance text.

    Only the start and the end of the text are inspected, so ordinary prose in
    the middle of a chapter is never second-guessed. Guidance is flagged, not
    removed: the person approving decides.
    """

    cleaned = normalize_newlines(text)
    warnings: list[BodyWarning] = []
    fence = _FENCE.match(cleaned)
    if fence:
        cleaned = fence.group("body")
        warnings.append(BodyWarning(index, "fence_removed", ""))
    if re.match(r"\A\s*---\s*\n", cleaned):
        raise EditError(
            "frontmatter_not_allowed",
            "write only the chapter body; frontmatter is managed by the plugin",
            index=index,
        )
    lines = [line for line in cleaned.split("\n") if line.strip()]
    if lines:
        first, last = lines[0], lines[-1]
        if _LEAD_IN.match(first):
            warnings.append(BodyWarning(index, "leading_guidance", first.strip()[:120]))
        if len(lines) > 1 or not _LEAD_IN.match(first):
            if _TRAILING.match(last):
                warnings.append(BodyWarning(index, "trailing_guidance", last.strip()[:120]))
        heading = _HEADING.match(first)
        if heading and title and _same_title(heading.group("title"), title):
            warnings.append(BodyWarning(index, "duplicate_title", first.strip()[:120]))
    return cleaned, warnings


def _same_title(heading: str, title: str) -> bool:
    left, right = heading.strip().casefold(), title.strip().casefold()
    return bool(left) and bool(right) and (left == right or right in left)


def check_edits(edits: Sequence[Edit], *, title: str | None = None) -> tuple[tuple[Edit, ...], list[BodyWarning]]:
    """Clean the text each edit would write and collect the warnings."""

    cleaned_edits: list[Edit] = []
    warnings: list[BodyWarning] = []
    for index, edit in enumerate(edits):
        values = {name: getattr(edit, name) for name in _FIELDS[edit.op]}
        for name in ("new_text", "content"):
            if name in values and values[name]:
                values[name], found = clean_body(values[name], index=index, title=title)
                warnings.extend(found)
        cleaned_edits.append(Edit(op=edit.op, **values))
    return tuple(cleaned_edits), warnings


# ------------------------------------------------------------------ previews
def build_previews(base_text: str, edits: Sequence[Edit]) -> list[dict[str, Any]]:
    """One preview per edit: the changed paragraphs before and after, with the
    character-level difference inside them."""

    text = normalize_newlines(base_text)
    previews: list[dict[str, Any]] = []
    for index, edit in enumerate(edits):
        after = _apply_one(text, edit, index)
        previews.append({"edit": index, "op": edit.op, "regions": _regions(text, after)})
        text = after
    return previews


def _regions(before: str, after: str) -> list[dict[str, Any]]:
    old_lines = before.split("\n")
    new_lines = after.split("\n")
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    regions: list[dict[str, Any]] = []
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old = "\n".join(old_lines[a1:a2])
        new = "\n".join(new_lines[b1:b2])
        regions.append({
            "old": old,
            "new": new,
            "line": a1 + 1,
            "inline": _inline(old, new),
        })
    return regions


def _inline(old: str, new: str) -> list[dict[str, str]]:
    if not old:
        return [{"op": "insert", "text": new}]
    if not new:
        return [{"op": "delete", "text": old}]
    if len(old) * len(new) > _INLINE_LIMIT:
        return [{"op": "delete", "text": old}, {"op": "insert", "text": new}]
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    parts: list[dict[str, str]] = []
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag == "equal":
            parts.append({"op": "equal", "text": old[a1:a2]})
            continue
        if a2 > a1:
            parts.append({"op": "delete", "text": old[a1:a2]})
        if b2 > b1:
            parts.append({"op": "insert", "text": new[b1:b2]})
    return parts
