"""
utils package — shared helpers and utilities.

Phase 2 modules
---------------
* :mod:`~text_extractors` — regex-based email, phone, link, and skill extraction.
* :mod:`~section_parser` — deterministic résumé section detection and parsing.
* :mod:`~date_parser` — multi-format date string → ``datetime.date`` converter.

All utilities are pure functions with no I/O side effects.
"""

from .date_parser import is_present, parse_date_string
from .section_parser import (
    detect_sections,
    parse_education_section,
    parse_experience_section,
)
from .text_extractors import (
    extract_emails,
    extract_links,
    extract_phones,
    extract_skills,
)

__all__ = [
    # text_extractors
    "extract_emails",
    "extract_phones",
    "extract_links",
    "extract_skills",
    # section_parser
    "detect_sections",
    "parse_experience_section",
    "parse_education_section",
    # date_parser
    "parse_date_string",
    "is_present",
]
