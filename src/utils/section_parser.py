"""
section_parser.py — deterministic section detection for résumé text.

Splits the raw text extracted from a PDF résumé into named sections
(EXPERIENCE, EDUCATION, SKILLS, etc.) and provides per-section parsers
that return canonical model objects.

Design rules
------------
* No NLP, no ML — only keyword matching and line-level heuristics.
* Functions are pure (no I/O, no side effects).
* All parsers return empty lists on empty / unrecognised input.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from src.models import Education, EducationDegree, Experience
from src.utils.date_parser import is_present, parse_date_string


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

# Maps known header aliases to canonical section names.
_SECTION_HEADERS: dict[str, str] = {
    # Experience
    "experience": "experience",
    "work experience": "experience",
    "professional experience": "experience",
    "work history": "experience",
    "employment": "experience",
    "employment history": "experience",
    "career history": "experience",
    "internship": "experience",
    # Education
    "education": "education",
    "academic background": "education",
    "academic history": "education",
    "qualifications": "education",
    "educational background": "education",
    # Skills
    "skills": "skills",
    "technical skills": "skills",
    "core competencies": "skills",
    "competencies": "skills",
    "technologies": "skills",
    "tools": "skills",
    # Summary
    "summary": "summary",
    "professional summary": "summary",
    "profile": "summary",
    "objective": "summary",
    "about": "summary",
    "overview": "summary",
}

# A header line is short (<= 60 chars), uppercase or title-case, and matches
# one of the known section keys.
_MAX_HEADER_LINE_LEN = 60


def _normalise_header(line: str) -> Optional[str]:
    """
    Return the canonical section name if ``line`` is a section header,
    otherwise return ``None``.
    """
    stripped = line.strip().lower().rstrip(":").strip()
    if len(stripped) > _MAX_HEADER_LINE_LEN:
        return None
    return _SECTION_HEADERS.get(stripped)


def detect_sections(lines: list[str]) -> dict[str, list[str]]:
    """
    Split a list of raw text lines into named sections.

    Parameters
    ----------
    lines:
        Lines of text extracted from a PDF page (or the entire document).

    Returns
    -------
    dict[str, list[str]]
        Mapping of canonical section name → list of content lines belonging
        to that section.  Lines before the first detected header are stored
        under the key ``"header"``.  Unrecognised inter-section text is
        discarded.

    Notes
    -----
    If the same section header appears more than once (e.g. two
    ``"EDUCATION"`` blocks), their content is concatenated.
    """
    sections: dict[str, list[str]] = {"header": []}
    current_section = "header"

    for line in lines:
        canonical = _normalise_header(line)
        if canonical is not None:
            current_section = canonical
            if canonical not in sections:
                sections[canonical] = []
        else:
            sections[current_section].append(line)

    return sections


# ---------------------------------------------------------------------------
# Experience section parser
# ---------------------------------------------------------------------------

# Date range pattern: "Jan 2020 - Present" or "2018 - 2021"
_DATE_RANGE_RE = re.compile(
    r"(?P<start>[A-Za-z]{3,9}\s+\d{4}|\d{4}(?:-\d{2})?)"
    r"\s*[-–—to]+\s*"
    r"(?P<end>[A-Za-z]{3,9}\s+\d{4}|\d{4}(?:-\d{2})?|[Pp]resent|[Cc]urrent|[Nn]ow)",
)

# Title/company separator heuristics: "Software Engineer at Google"
_AT_SEPARATOR_RE = re.compile(r"\bat\b", re.IGNORECASE)
_PIPE_SEPARATOR_RE = re.compile(r"\s+[|•·]\s+")


def _parse_title_company(line: str) -> tuple[Optional[str], Optional[str]]:
    """
    Attempt to split a line into ``(title, company)`` using common separators.

    Tries: ` at `, pipe ``|``, bullet ``•``, comma ``,``.
    Returns ``(line, None)`` if no separator is found.
    """
    # "Engineer at Google"
    m = _AT_SEPARATOR_RE.search(line)
    if m:
        return line[: m.start()].strip() or None, line[m.end() :].strip() or None

    # "Engineer | Google"  or  "Engineer • Google"
    m = _PIPE_SEPARATOR_RE.search(line)
    if m:
        return line[: m.start()].strip() or None, line[m.end() :].strip() or None

    # "Engineer, Google" — only if comma present and both parts are non-empty
    if "," in line:
        parts = line.split(",", 1)
        if all(p.strip() for p in parts):
            return parts[0].strip(), parts[1].strip()

    return line.strip() or None, None


def parse_experience_section(lines: list[str]) -> list[Experience]:
    """
    Parse raw experience section lines into a list of ``Experience`` objects.

    Strategy
    --------
    1. Scan lines for a date range (e.g. ``"Jan 2020 - Present"``).
    2. The line immediately before the date range is the title/company line.
    3. Lines after the date range (until the next date range) are description.

    Parameters
    ----------
    lines:
        Raw text lines from the experience section.

    Returns
    -------
    list[Experience]
        Parsed experience entries, ordered as they appear in the source.
        Returns an empty list if no date ranges are detected.
    """
    experiences: list[Experience] = []
    non_empty = [ln for ln in lines if ln.strip()]

    i = 0
    while i < len(non_empty):
        line = non_empty[i]
        date_match = _DATE_RANGE_RE.search(line)

        if date_match:
            # Title/company: look on the same line (before dates) or previous line.
            before_dates = line[: date_match.start()].strip()
            if before_dates:
                title, company = _parse_title_company(before_dates)
            elif i > 0:
                title, company = _parse_title_company(non_empty[i - 1])
            else:
                title, company = None, None

            start_date: Optional[date] = parse_date_string(date_match.group("start"))
            end_raw: str = date_match.group("end")
            end_date: Optional[date] = None if is_present(end_raw) else parse_date_string(end_raw)
            is_current: bool = is_present(end_raw)

            # Collect description lines until next date range.
            desc_lines: list[str] = []
            j = i + 1
            while j < len(non_empty) and not _DATE_RANGE_RE.search(non_empty[j]):
                desc_lines.append(non_empty[j].strip())
                j += 1

            experiences.append(
                Experience(
                    title=title,
                    company=company,
                    start=date_match.group("start"),
                    end=end_raw,
                    start_date=start_date,
                    end_date=end_date,
                    is_current=is_current,
                    summary="\n".join(desc_lines) if desc_lines else None,
                    source="resume",
                )
            )
            i = j
        else:
            i += 1

    return experiences


# ---------------------------------------------------------------------------
# Education section parser
# ---------------------------------------------------------------------------

# Maps common degree keywords to EducationDegree enum values.
_DEGREE_KEYWORDS: dict[str, EducationDegree] = {
    "phd": EducationDegree.DOCTORATE,
    "ph.d": EducationDegree.DOCTORATE,
    "doctorate": EducationDegree.DOCTORATE,
    "doctor": EducationDegree.DOCTORATE,
    "master": EducationDegree.MASTER,
    "m.s": EducationDegree.MASTER,
    "m.sc": EducationDegree.MASTER,
    "mba": EducationDegree.MASTER,
    "m.tech": EducationDegree.MASTER,
    "bachelor": EducationDegree.BACHELOR,
    "b.s": EducationDegree.BACHELOR,
    "b.sc": EducationDegree.BACHELOR,
    "b.e": EducationDegree.BACHELOR,
    "b.tech": EducationDegree.BACHELOR,
    "b.a": EducationDegree.BACHELOR,
    "associate": EducationDegree.ASSOCIATE,
    "a.s": EducationDegree.ASSOCIATE,
    "a.a": EducationDegree.ASSOCIATE,
    "high school": EducationDegree.HIGH_SCHOOL,
    "secondary": EducationDegree.HIGH_SCHOOL,
    "diploma": EducationDegree.CERTIFICATE,
    "certificate": EducationDegree.CERTIFICATE,
    "bootcamp": EducationDegree.BOOTCAMP,
}


def _detect_degree(text: str) -> EducationDegree:
    """Return the best matching ``EducationDegree`` for ``text``."""
    lower = text.lower()
    for keyword, degree in _DEGREE_KEYWORDS.items():
        if keyword in lower:
            return degree
    return EducationDegree.UNKNOWN


def parse_education_section(lines: list[str]) -> list[Education]:
    """
    Parse raw education section lines into a list of ``Education`` objects.

    Strategy
    --------
    1. Group lines into blocks separated by blank lines or date ranges.
    2. For each block, detect degree keyword, institution, field of study,
       and date range.

    Parameters
    ----------
    lines:
        Raw text lines from the education section.

    Returns
    -------
    list[Education]
        Parsed education entries.  Returns an empty list on empty input.
    """
    educations: list[Education] = []
    non_empty = [ln for ln in lines if ln.strip()]

    if not non_empty:
        return []

    # Split blocks only on date-range lines.  Degree keywords are detected
    # *within* each block to avoid false splits when degree + field appear
    # on the same line (e.g. "Bachelor of Technology in Computer Science").
    block_starts: list[int] = [0]
    for idx, line in enumerate(non_empty):
        if idx > 0 and _DATE_RANGE_RE.search(line):
            block_starts.append(idx)

    block_starts = sorted(set(block_starts))

    for b_idx, start in enumerate(block_starts):
        end = block_starts[b_idx + 1] if b_idx + 1 < len(block_starts) else len(non_empty)
        block = non_empty[start:end]
        if not block:
            continue

        degree = EducationDegree.UNKNOWN
        institution: Optional[str] = None
        field_of_study: Optional[str] = None
        start_date: Optional[date] = None
        end_date: Optional[date] = None
        is_completed: bool = True

        for line in block:
            # Try to extract date range.
            dm = _DATE_RANGE_RE.search(line)
            if dm:
                start_date = parse_date_string(dm.group("start"))
                end_raw = dm.group("end")
                if is_present(end_raw):
                    is_completed = False
                    end_date = None
                else:
                    end_date = parse_date_string(end_raw)
                # Text before the date range may contain degree/institution.
                before = line[: dm.start()].strip()
                if before:
                    deg = _detect_degree(before)
                    if deg != EducationDegree.UNKNOWN:
                        degree = deg
                    if institution is None:
                        institution = before
                continue

            # Check for degree keyword in the line.
            detected = _detect_degree(line)
            if detected != EducationDegree.UNKNOWN and degree == EducationDegree.UNKNOWN:
                degree = detected
                # Try to extract field of study: text after the degree keyword.
                for kw in _DEGREE_KEYWORDS:
                    if kw in line.lower():
                        after = re.split(re.escape(kw), line, flags=re.IGNORECASE, maxsplit=1)
                        if len(after) > 1 and after[1].strip():
                            field_of_study = after[1].strip().lstrip(".,- in")
                        break
                # If the full line just *is* the degree line, don't treat it as institution.
                continue

            # Remaining lines are likely institution names.
            if institution is None:
                institution = line.strip()

        # Post-processing using deterministic regex
        gpa: Optional[float] = None
        if field_of_study:
            # Extract GPA like "CGPA: 9.57" or "GPA 3.8"
            gpa_match = re.search(r'(?:c?gpa|score|grade)[\s:–-]*([\d.]+)', field_of_study, re.IGNORECASE)
            if gpa_match:
                try:
                    gpa = float(gpa_match.group(1))
                except ValueError:
                    pass
            # Clean up field_of_study by removing the GPA part
            field_of_study = re.sub(r'[\s–-]*c?gpa[\s:–-]*[\d.]+', '', field_of_study, flags=re.IGNORECASE).strip()
            
        if institution:
            # Extract expected graduation year like "Expected Aug 2027"
            year_match = re.search(r'(?:expected|graduating)\s+(?:[a-zA-Z]+\s+)?(\d{4})', institution, re.IGNORECASE)
            if year_match:
                end_date_str = year_match.group(1)
                end_date = parse_date_string(end_date_str)
                is_completed = False
            # Clean up institution by removing location and expected date
            institution = re.sub(r',?\s+(?:bangalore|mumbai|pune|delhi|hyderabad|chennai|kolkata|india).*$', '', institution, flags=re.IGNORECASE)
            institution = re.sub(r'[\s,]*expected.*$', '', institution, flags=re.IGNORECASE).strip()

        # Only append if we have at least something meaningful.
        if degree != EducationDegree.UNKNOWN or institution or start_date:
            educations.append(
                Education(
                    institution=institution,
                    degree=degree,
                    field=field_of_study,
                    end_year=str(end_date.year) if end_date else None,
                    start_date=start_date,
                    is_completed=is_completed,
                    gpa=gpa,
                    source="resume",
                )
            )

    return educations
