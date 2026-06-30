"""
text_extractors.py — pure regex-based extraction helpers.

All functions in this module are **pure** (no I/O, no side effects) and
operate solely on raw text strings.  They are intentionally decoupled from
any adapter so they can be unit-tested in complete isolation.

Extraction philosophy
---------------------
* Use deterministic regex patterns only — no NLP, no external APIs.
* Return empty lists / dicts on no-match; never raise on valid input.
* Callers (adapters) are responsible for mapping results to canonical models.
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Email extraction
# ---------------------------------------------------------------------------

# RFC 5322-inspired pattern (pragmatic subset — covers 99%+ of real addresses).
_EMAIL_PATTERN: re.Pattern[str] = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)


def extract_emails(text: str) -> list[str]:
    """
    Extract all email addresses from ``text`` using regex.

    Parameters
    ----------
    text:
        Raw input string (e.g. full résumé text or ATS JSON value).

    Returns
    -------
    list[str]
        Deduplicated list of email addresses found, lowercased and ordered by
        first appearance.  Returns an empty list when none are found.

    Examples
    --------
    >>> extract_emails("Contact me at john.doe@example.com or jd@work.io")
    ['john.doe@example.com', 'jd@work.io']
    >>> extract_emails("No email here")
    []
    """
    if not text:
        return []
    seen: set[str] = set()
    results: list[str] = []
    for match in _EMAIL_PATTERN.finditer(text):
        normalised = match.group().lower()
        if normalised not in seen:
            seen.add(normalised)
            results.append(normalised)
    return results


# ---------------------------------------------------------------------------
# Phone extraction
# ---------------------------------------------------------------------------

# Covers international (+91 98765 43210), US (415-555-0100), and compact forms.
_PHONE_PATTERNS: list[re.Pattern[str]] = [
    # International: +<country> <digits with spaces/dashes>
    re.compile(r"\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,9}"),
    # US/CA: (NXX) NXX-XXXX or NXX-NXX-XXXX
    re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}"),
    # Compact 10-digit run (India, etc.)
    re.compile(r"\b\d{10}\b"),
]

# Minimum digits required to consider a match a real phone number.
_MIN_PHONE_DIGITS = 7


def _count_digits(s: str) -> int:
    """Return the count of digit characters in ``s``."""
    return sum(c.isdigit() for c in s)


def extract_phones(text: str) -> list[str]:
    """
    Extract phone numbers from ``text`` using a set of regex patterns.

    The function deduplicates by the digit-only form of each match to avoid
    returning the same number in multiple formats.

    Parameters
    ----------
    text:
        Raw input string.

    Returns
    -------
    list[str]
        Deduplicated list of phone number strings as found in the text
        (preserving original formatting).  Returns an empty list when none
        are found or when matches contain too few digits.

    Examples
    --------
    >>> extract_phones("Call +91 9876543210 or (415) 555-0100")
    ['+91 9876543210', '(415) 555-0100']
    >>> extract_phones("Reference: 12345")
    []
    """
    if not text:
        return []

    seen_digits: set[str] = set()
    results: list[str] = []

    for pattern in _PHONE_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group().strip()
            digits_only = re.sub(r"\D", "", raw)
            if len(digits_only) < _MIN_PHONE_DIGITS:
                continue
            if digits_only not in seen_digits:
                seen_digits.add(digits_only)
                results.append(raw)

    return results


# ---------------------------------------------------------------------------
# Link extraction
# ---------------------------------------------------------------------------

_LINK_PATTERNS: dict[str, re.Pattern[str]] = {
    "linkedin": re.compile(
        r"https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+/?",
        re.IGNORECASE,
    ),
    "github": re.compile(
        r"https?://(?:www\.)?github\.com/[A-Za-z0-9\-_%]+/?",
        re.IGNORECASE,
    ),
}


def extract_links(text: str) -> dict[str, list[str]]:
    """
    Extract LinkedIn and GitHub profile URLs from ``text``.

    Parameters
    ----------
    text:
        Raw input string.

    Returns
    -------
    dict[str, list[str]]
        A dictionary with keys ``"linkedin"`` and ``"github"``, each mapping
        to a deduplicated list of matching URLs.  Empty lists when no URLs
        of that type are found.

    Examples
    --------
    >>> result = extract_links("See https://linkedin.com/in/johndoe")
    >>> result["linkedin"]
    ['https://linkedin.com/in/johndoe']
    >>> result["github"]
    []
    """
    results: dict[str, list[str]] = {key: [] for key in _LINK_PATTERNS}
    if not text:
        return results

    for key, pattern in _LINK_PATTERNS.items():
        seen: set[str] = set()
        for match in pattern.finditer(text):
            url = match.group().rstrip("/")
            if url not in seen:
                seen.add(url)
                results[key].append(url)

    return results


# ---------------------------------------------------------------------------
# Skill extraction
# ---------------------------------------------------------------------------

def extract_skills(
    text: str,
    taxonomy: dict[str, str],
) -> list[str]:
    """
    Detect skills in ``text`` by matching against a configurable taxonomy.

    Matching is **case-insensitive** and uses whole-word boundary detection
    so that e.g. ``"go"`` does not match inside ``"golang"``.

    Parameters
    ----------
    text:
        Raw input string (e.g. full résumé text).
    taxonomy:
        A mapping of ``{lowercase_keyword: canonical_display_name}``.
        Example: ``{"python": "Python", "ml": "Machine Learning"}``.

    Returns
    -------
    list[str]
        Ordered, deduplicated list of **canonical** skill names found in
        ``text``.  Order follows the iteration order of ``taxonomy``.

    Examples
    --------
    >>> taxonomy = {"python": "Python", "react": "React"}
    >>> extract_skills("I know Python and React.js", taxonomy)
    ['Python', 'React']
    """
    if not text or not taxonomy:
        return []

    text_lower = text.lower()
    found: list[str] = []
    seen_canonical: set[str] = set()

    for keyword, canonical in taxonomy.items():
        # Escape special regex chars in multi-word keywords (e.g. "c++", "machine learning")
        escaped = re.escape(keyword)
        # Word boundary on left; allow non-word on right for things like "Node.js"
        pattern = re.compile(r"(?<![a-zA-Z0-9])" + escaped + r"(?![a-zA-Z0-9])", re.IGNORECASE)
        if pattern.search(text_lower) and canonical not in seen_canonical:
            seen_canonical.add(canonical)
            found.append(canonical)

    return found
