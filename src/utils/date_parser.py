"""
date_parser.py — multi-format date string parser.

Converts free-text date strings found in résumés and ATS exports into
``datetime.date`` objects.  All functions are pure and raise no exceptions
on unrecognised input (they return ``None`` instead).

Supported formats
-----------------
* ``"Jan 2020"`` / ``"January 2020"``
* ``"2020-01"`` / ``"2020-01-15"``
* ``"2020"`` (year-only → January 1st of that year)
* ``"Present"`` / ``"Current"`` / ``"Now"`` → ``None`` (caller treats as current)
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MONTH_MAP: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12,
}

_PRESENT_TOKENS: frozenset[str] = frozenset(
    {"present", "current", "now", "till date", "to date", "ongoing"}
)

# Regex patterns, ordered from most specific to least specific.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # ISO: 2020-01-15
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "iso_full"),
    # ISO month: 2020-01
    (re.compile(r"^(\d{4})-(\d{2})$"), "iso_month"),
    # Month name + year: "Jan 2020" or "January 2020"
    (re.compile(r"^([A-Za-z]+)[\s,]+(\d{4})$"), "month_name_year"),
    # Year only: "2020"
    (re.compile(r"^(\d{4})$"), "year_only"),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_date_string(raw: str) -> Optional[date]:
    """
    Parse a free-text date string into a ``datetime.date``.

    Parameters
    ----------
    raw:
        The raw date string to parse (e.g. ``"Jan 2020"``, ``"2020-03"``).

    Returns
    -------
    datetime.date or None
        Parsed date, or ``None`` if the string represents "present" /
        "current" or cannot be parsed.

    Examples
    --------
    >>> parse_date_string("Jan 2020")
    datetime.date(2020, 1, 1)
    >>> parse_date_string("2020-06")
    datetime.date(2020, 6, 1)
    >>> parse_date_string("Present")
    # returns None
    >>> parse_date_string("garbage")
    # returns None
    """
    if not raw:
        return None

    stripped = raw.strip()

    # Check for "present"-style tokens first.
    if stripped.lower() in _PRESENT_TOKENS:
        return None

    for pattern, fmt in _PATTERNS:
        m = pattern.match(stripped)
        if not m:
            continue

        try:
            if fmt == "iso_full":
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if fmt == "iso_month":
                return date(int(m.group(1)), int(m.group(2)), 1)
            if fmt == "month_name_year":
                month_str = m.group(1).lower()
                month = _MONTH_MAP.get(month_str)
                if month is None:
                    continue
                return date(int(m.group(2)), month, 1)
            if fmt == "year_only":
                return date(int(m.group(1)), 1, 1)
        except ValueError:
            # e.g. invalid day/month combination — skip.
            continue

    return None


def is_present(raw: str) -> bool:
    """
    Return ``True`` if ``raw`` represents an ongoing / current date.

    Parameters
    ----------
    raw:
        Raw date string (e.g. ``"Present"``, ``"Current"``).

    Examples
    --------
    >>> is_present("Present")
    True
    >>> is_present("Jan 2020")
    False
    """
    return raw.strip().lower() in _PRESENT_TOKENS
