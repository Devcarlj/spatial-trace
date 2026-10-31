"""Structured temporal/attribute intent parsed from a natural-language query.

Parsing is deterministic and model-free so the same phrasing always routes the
same way in mock, live, tests, and the evaluator. The model normalizer still
supplies synonyms; this module only adds structure on top of its output:

- temporal kind: locate / last_seen / first_seen / moved
- attribute split: "<base> wearing|in|with <attribute>" for any base object
  (previously only hard-coded person phrases reached attribute verification),
  plus a leading colour/material adjective ("red mug" -> base "mug",
  attribute "red").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

COLOURS = {
    "black", "white", "red", "orange", "yellow", "green", "blue", "purple",
    "pink", "brown", "grey", "gray", "silver", "gold", "beige", "striped",
    "checked", "floral", "dark", "light",
}

_LAST_SEEN = re.compile(
    r"\b(last time|last seen|latest appearance|most recent|when (?:was|did) .{0,60}? last seen)\b", re.I)
_FIRST_SEEN = re.compile(
    r"\b(first time|first seen|first appear|earliest appearance|when (?:did|was) .{0,60}? first)\b", re.I)
_MOVED = re.compile(r"\b(did|has|have|was) .{0,60}? \b(moved|move|displaced)\b|\bhas .{0,40}? moved\b", re.I)

# Scaffolding that must not leak into the object phrase, e.g.
# "what is the last time there is a person wearing a blue vest".
_SCAFFOLD = [
    re.compile(r"^(?:what|when) (?:is|was) the (?:last|first|latest|earliest) time (?:there (?:is|was) |we (?:see|saw) |you (?:see|saw) )?(?:a |an |the )?", re.I),
    re.compile(r"^(?:when|where) (?:was|were|did|do) (?:we |you )?(?:last |first )?(?:see|seen|saw|find|found)?\s*(?:the |a |an )?", re.I),
    re.compile(r"^(?:did|has|have|was|were) (?:the |a |an )?", re.I),
    re.compile(r"^(?:where (?:is|are|was|were)|find|locate|show(?: me)?|search for)\s+(?:the |a |an |my )?", re.I),
    re.compile(r"^(?:the |a |an )", re.I),
]
_TRAILING = re.compile(r"\s+(?:last|first)\s+(?:seen|appear\w*)$|\s+(?:moved|move)$", re.I)


@dataclass(frozen=True)
class QueryIntent:
    kind: str  # locate | last_seen | first_seen | moved
    target: str  # full phrase used for retrieval (base + attribute context)
    base_object: str
    attribute: str | None = None

    @property
    def verification_phrase(self) -> str:
        """Phrase handed to frame verification (attribute split happens there)."""
        return self.target


def split_attribute(phrase: str) -> tuple[str, str | None]:
    """Split "<base> wearing/in/with <attr>" or a leading colour adjective."""
    text = " ".join(phrase.strip().lower().split())
    match = re.fullmatch(r"(.+?) (?:wearing|in|with) (.+)", text)
    if match and len(match.group(1).split()) <= 4:
        base = re.sub(r"^(?:a |an )", "", match.group(1)).strip()
        attribute = re.sub(r"^(?:a |an )", "", match.group(2)).strip()
        return base, attribute
    words = text.split()
    if len(words) >= 2 and words[0] in COLOURS:
        return " ".join(words[1:]), words[0]
    return text, None


def _clean_target(text: str) -> str:
    cleaned = text.strip().lower().rstrip("?.! ")
    for pattern in _SCAFFOLD:
        cleaned = pattern.sub("", cleaned, count=1).strip()
    cleaned = _TRAILING.sub("", cleaned).strip()
    cleaned = re.sub(r"^(?:there (?:is|was) )?(?:a |an |the )?", "", cleaned)
    return cleaned or text.strip().lower().rstrip("?.! ")


def parse_intent(original_query: str, normalized: str) -> QueryIntent:
    original = original_query.strip()
    if _LAST_SEEN.search(original):
        kind = "last_seen"
    elif _FIRST_SEEN.search(original):
        kind = "first_seen"
    elif _MOVED.search(original) or re.search(r"\bdid .{0,60}? move\b", original, re.I):
        kind = "moved"
    else:
        kind = "locate"
    # The normalizer output wins: it carries synonym expansion ("specs" ->
    # "reading glasses"). It can retain temporal scaffolding ("the last time
    # there is a person..."), which the cleaner strips; only if cleaning the
    # normalizer output still leaves scaffolding behind do we fall back to
    # cleaning the raw question.
    target = _clean_target(normalized)
    if not target or re.search(r"\b(last|first) time\b|\bthere (?:is|was)\b", target):
        target = _clean_target(original) or target
    if kind == "moved":
        target = _TRAILING.sub("", target).strip() or target
    base, attribute = split_attribute(target)
    return QueryIntent(kind=kind, target=target, base_object=base, attribute=attribute)
