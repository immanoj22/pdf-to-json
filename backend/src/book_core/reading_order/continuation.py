"""Rule-based evidence that one line's text continues on another line.

Only Unicode properties are used: sentence terminals (``Sentence_Terminal``), letter case
(``Ll``/``Lu``/``Lt``; caseless scripts give no case evidence), closing punctuation and
line-break hyphens. An optional whole-book vocabulary (Step 6 casefolded frequencies) attests a
hyphenated join. No model is used. Scores are heuristics in [-1, 1], not probabilities:
positive means the text continues, negative means a break (paragraph or block end).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

import regex

# The ledger's benchmark token rule (Unicode letters, marks, numbers); a test keeps them equal.
TOKEN_PATTERN = regex.compile(r"[\p{L}\p{M}\p{N}]+")

HYPHENS = "-­‐‑"
_TRAILING_CLOSERS = regex.compile(r"[\p{Pe}\p{Pf}\p{Pi}\"'\s]*$")
_TERMINAL = regex.compile(r"\p{Sentence_Terminal}$")
_FIRST_LETTER = regex.compile(r"[\p{L}\p{N}]")
_CONTINUING_START = regex.compile(r"^[\p{Pe}\p{Pf},;:、،]")
CONTINUES = 0.4
BREAKS = -0.2
HEADING_TYPES = frozenset({"title_candidate", "heading_candidate"})


@dataclass(frozen=True)
class Evidence:
    score: float
    reasons: list[str] = field(default_factory=list)
    features: dict = field(default_factory=dict)

    @property
    def verdict(self):
        if self.score >= CONTINUES:
            return "continues"
        return "break" if self.score <= BREAKS else "neutral"


def ending(text):
    """How a line ends: hyphen (a word broken across lines), terminal, or open."""
    stripped = text.rstrip()
    if not stripped:
        return "empty"
    if stripped[-1] in HYPHENS and len(stripped) > 1 and regex.match(r"\p{L}", stripped[-2]):
        return "hyphen"
    core = _TRAILING_CLOSERS.sub("", stripped)
    if core and _TERMINAL.search(core):
        return "terminal"
    return "open"


def beginning(text):
    """How a line starts: continuing punctuation, lower/upper case, caseless letter or digit."""
    stripped = text.lstrip()
    if not stripped:
        return "empty"
    if _CONTINUING_START.match(stripped):
        return "continuing_punctuation"
    match = _FIRST_LETTER.search(stripped)
    if match is None:
        return "symbol"
    character = match.group()
    if regex.match(r"\p{Ll}", character):
        return "lower"
    if regex.match(r"[\p{Lu}\p{Lt}]", character):
        return "upper"
    if regex.match(r"\p{N}", character):
        return "digit"
    return "caseless"


def hyphen_join(previous, following, vocabulary):
    """The word joined across a line-break hyphen, and how often the book spells it so."""
    left = list(TOKEN_PATTERN.finditer(previous.rstrip()[:-1]))
    right = TOKEN_PATTERN.search(following)
    if not left or right is None:
        return None, 0
    joined = left[-1].group() + right.group()
    return joined, int(vocabulary.get(joined.casefold(), 0)) if vocabulary else 0


def continuation(
    previous: str,
    following: str,
    *,
    previous_type: str | None = None,
    following_type: str | None = None,
    vocabulary: Mapping[str, int] | None = None,
) -> Evidence:
    """Evidence that ``following`` continues the text that ``previous`` ends."""
    end, start = ending(previous), beginning(following)
    score, reasons = 0.0, []
    features = {"previous_end": end, "following_start": start}
    if end == "hyphen":
        score += 0.5
        reasons.append("previous line ends with a line-break hyphen")
        joined, count = hyphen_join(previous, following, vocabulary)
        features["hyphen_join_attested"] = count
        if count:
            score += 0.3
            reasons.append(f"joined spelling attested {count}x in the book vocabulary")
    elif end == "open":
        score += 0.3
        reasons.append("previous line has no sentence terminal")
    elif end == "terminal":
        score -= 0.2
        reasons.append("previous line ends a sentence")
    if start == "lower":
        score += 0.35
        reasons.append("next line starts lowercase")
    elif start == "continuing_punctuation":
        score += 0.3
        reasons.append("next line starts with continuing punctuation")
    elif start == "upper":
        score -= 0.15 if end == "terminal" else 0.05
        reasons.append("next line starts uppercase")
    elif start == "caseless":
        reasons.append("caseless script: no case evidence")
    if following_type in HEADING_TYPES:
        score -= 0.6
        reasons.append("next line is a heading/title candidate")
    if previous_type in HEADING_TYPES:
        score -= 0.3
        reasons.append("previous line is a heading/title candidate")
    score = max(-1.0, min(1.0, round(score, 3)))
    return Evidence(score, reasons or ["no continuation evidence"], features)
