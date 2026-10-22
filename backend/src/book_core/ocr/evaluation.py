"""Counted OCR errors and held-out review calibration, with explicit token conventions."""

import hashlib
import json
import unicodedata
from collections import Counter

import regex
from rapidfuzz.distance import Levenshtein


def normalized(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def words(text, *, cjk=False):
    """Evaluation only: CJK uses characters; the native ledger tokenizer is unchanged."""
    value = normalized(text)
    if cjk:
        return regex.findall(
            r"[\p{Han}\p{Hiragana}\p{Katakana}]|[^\s\p{Han}\p{Hiragana}\p{Katakana}]+", value
        )
    return value.split()


def error_counts(reference, hypothesis, *, cjk=False):
    expected, observed = normalized(reference), normalized(hypothesis)
    ref_words, hyp_words = words(reference, cjk=cjk), words(hypothesis, cjk=cjk)
    chars = Levenshtein.distance(expected, observed)
    tokens = Levenshtein.distance(ref_words, hyp_words)
    return {
        "characters": len(expected),
        "character_errors": chars,
        "words": len(ref_words),
        "word_errors": tokens,
        "cer": chars / len(expected) if expected else None,
        "wer": tokens / len(ref_words) if ref_words else None,
        "word_rule": "CJK character plus non-CJK whitespace token" if cjk else "whitespace",
    }


def aggregate(rows):
    totals = Counter()
    for row in rows:
        totals.update(
            {key: row[key] for key in ("characters", "character_errors", "words", "word_errors")}
        )
    return {
        **totals,
        "cer": totals["character_errors"] / totals["characters"] if totals["characters"] else None,
        "wer": totals["word_errors"] / totals["words"] if totals["words"] else None,
    }


def word_errors(reference_words, hypothesis_words):
    """One error label per emitted word; deletions are reported separately, never hidden."""
    wrong = [False] * len(hypothesis_words)
    deletions = 0
    for operation in Levenshtein.opcodes(reference_words, hypothesis_words):
        if operation.tag == "equal":
            continue
        for index in range(operation.dest_start, operation.dest_end):
            wrong[index] = True
        deletions += max(
            0, operation.src_end - operation.src_start - (operation.dest_end - operation.dest_start)
        )
    return wrong, deletions


def calibration_counts(observations, threshold):
    counts = Counter(flagged=0, flagged_wrong=0, unflagged=0, unflagged_wrong=0)
    for score, wrong in observations:
        category = "flagged" if score < threshold else "unflagged"
        counts[category] += 1
        counts[category + "_wrong"] += int(wrong)
    return {
        **counts,
        "flagged_error_rate": counts["flagged_wrong"] / counts["flagged"]
        if counts["flagged"]
        else None,
        "unflagged_error_rate": counts["unflagged_wrong"] / counts["unflagged"]
        if counts["unflagged"]
        else None,
    }


def fit_threshold(observations):
    """Maximise error-detection F1 on training data only, ties choose fewer review flags."""
    if not observations or not any(wrong for _, wrong in observations):
        raise ValueError("Calibration needs measured errors; an all-correct sample cannot fit it")
    best = None
    for threshold in sorted({0.0, 1.0, *(min(1.0, score + 1e-9) for score, _ in observations)}):
        counts = calibration_counts(observations, threshold)
        tp = counts["flagged_wrong"]
        fp = counts["flagged"] - tp
        fn = counts["unflagged_wrong"]
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        key = (f1, -counts["flagged"])
        if best is None or key > best[0]:
            best = (key, threshold, counts)
    return {
        "threshold": best[1],
        "training": best[2],
        "error_detection_f1": best[0][0],
        "sample_sha256": hashlib.sha256(
            json.dumps(observations, separators=(",", ":")).encode()
        ).hexdigest(),
    }
