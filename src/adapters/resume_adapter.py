"""
Resume PDF adapter — Phase 2 implementation.

Extracts candidate data from an unstructured résumé PDF using
``pdfplumber`` for text extraction and a suite of deterministic
regex/keyword-based extractors for entity detection.

Design rules
------------
* **No NLP, no ML, no external APIs** — only regex and keyword matching.
* The adapter is **fault-tolerant at the page level**: if a single page
  fails to extract, its text is silently skipped and extraction continues
  on remaining pages.
* A corrupt PDF that yields zero text returns an **empty profile** rather
  than raising (only a total open failure raises ``AdapterError``).
* All extraction logic lives in ``src/utils/`` — this adapter is a thin
  orchestration layer.

Provenance metadata
-------------------
Every extracted field gets a :class:`~src.models.ProvenanceRecord` with:
* ``source`` = the PDF filename
* ``confidence`` = 0.75 (lower than ATS due to unstructured nature)
* ``notes`` = ``"method=regex"`` or ``"method=section_keyword"``
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from pydantic import HttpUrl, ValidationError

from src.adapters.base import AdapterError, SourceAdapter
from src.models import (
    CandidateProfile,
    Location,
    ProvenanceRecord,
    Skill,
)
from src.utils.section_parser import (
    detect_sections,
    parse_education_section,
    parse_experience_section,
)
from src.utils.text_extractors import (
    extract_emails,
    extract_links,
    extract_phones,
    extract_skills,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default skill taxonomy (loaded from config/skill_taxonomy.json if available)
# ---------------------------------------------------------------------------

_DEFAULT_TAXONOMY_PATH = (
    Path(__file__).parent.parent.parent / "config" / "skill_taxonomy.json"
)

def _load_taxonomy(path: Optional[Path] = None) -> dict[str, str]:
    """
    Load the skill taxonomy from a JSON file.

    Falls back to an empty dict if the file is missing or malformed
    (extraction will still work, just return no skills).

    Parameters
    ----------
    path:
        Path to the taxonomy JSON.  Defaults to ``config/skill_taxonomy.json``
        relative to the project root.
    """
    target = path or _DEFAULT_TAXONOMY_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        # Strip the internal comment key if present.
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        logger.warning("Could not load skill taxonomy from %s: %s", target, exc)
        return {}


# ---------------------------------------------------------------------------
# Name extraction heuristic
# ---------------------------------------------------------------------------

def _extract_name_heuristic(header_lines: list[str]) -> Optional[str]:
    """
    Attempt to identify the candidate's full name from the résumé header.

    Strategy: the first non-empty, non-contact-info line in the "header"
    section (before any detected section) is most likely the name.

    A line is rejected as a name candidate if it contains:
    * An ``@`` (email address)
    * A digit run that looks like a phone number
    * A URL
    * Common section header keywords

    Parameters
    ----------
    header_lines:
        Lines from the ``"header"`` section returned by ``detect_sections()``.

    Returns
    -------
    str or None
        Best-guess full name, or ``None`` if no suitable line is found.
    """
    import re

    _REJECT_PATTERNS = [
        re.compile(r"@"),                          # email
        re.compile(r"\d{7,}"),                     # phone / long digit run
        re.compile(r"https?://", re.IGNORECASE),   # URL
        re.compile(r"linkedin\.com", re.IGNORECASE),
        re.compile(r"github\.com", re.IGNORECASE),
        re.compile(                                # section headers
            r"^\s*(resume|curriculum vitae|cv|portfolio|profile)\s*$",
            re.IGNORECASE,
        ),
    ]
    _BLACKLIST = {"resume", "cv", "curriculum vitae"}
    _MAX_NAME_WORDS = 6
    _MIN_NAME_CHARS = 2

    for line in header_lines:
        stripped = line.strip()
        if not stripped or len(stripped) < _MIN_NAME_CHARS:
            continue
        if stripped.lower() in _BLACKLIST:
            continue
        if any(p.search(stripped) for p in _REJECT_PATTERNS):
            continue
        words = stripped.split()
        if 1 <= len(words) <= _MAX_NAME_WORDS:
            return stripped

    return None


def _extract_headline_heuristic(header_lines: list[str], full_name: Optional[str]) -> Optional[str]:
    import re
    keywords = re.compile(r"\b(engineer|developer|intern|manager|architect|scientist|analyst|designer)\b", re.IGNORECASE)
    for line in header_lines:
        stripped = line.strip()
        if stripped == full_name:
            continue
        if keywords.search(stripped) and len(stripped.split()) <= 6:
            return stripped
    return None


def _extract_location_heuristic(header_lines: list[str]) -> Optional[str]:
    import re
    cities = re.compile(r"\b(Bangalore|Bengaluru|Mumbai|Delhi|Hyderabad|Pune)\b", re.IGNORECASE)
    for line in header_lines:
        match = cities.search(line)
        if match:
            return match.group(1).capitalize()
    return None

# ---------------------------------------------------------------------------
# Main adapter class
# ---------------------------------------------------------------------------

class ResumeAdapter(SourceAdapter):
    """
    Adapter for unstructured résumé PDFs.

    Orchestrates PDF text extraction via ``pdfplumber`` and delegates all
    entity extraction to the stateless utilities in ``src/utils/``.

    Parameters
    ----------
    path:
        Filesystem path to the résumé PDF file.
    skill_taxonomy:
        Optional custom skill taxonomy dict ``{keyword: canonical_name}``.
        If not provided, the adapter loads ``config/skill_taxonomy.json``.
    taxonomy_path:
        Optional path to a custom taxonomy JSON file.  Ignored if
        ``skill_taxonomy`` is provided directly.

    Example
    -------
    ::

        adapter = ResumeAdapter(path=Path("inputs/resume.pdf"))
        adapter.validate_source()
        profile = adapter.parse()
    """

    source_name: str = "resume"

    def __init__(
        self,
        path: Path,
        skill_taxonomy: Optional[dict[str, str]] = None,
        taxonomy_path: Optional[Path] = None,
    ) -> None:
        self.path = Path(path)
        self._taxonomy: Optional[dict[str, str]] = skill_taxonomy
        self._taxonomy_path: Optional[Path] = taxonomy_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_taxonomy(self) -> dict[str, str]:
        """Return the effective skill taxonomy, loading from disk if needed."""
        if self._taxonomy is not None:
            return self._taxonomy
        return _load_taxonomy(self._taxonomy_path)

    def _extract_text(self) -> str:
        """
        Open the PDF and concatenate text from all pages.

        Page-level failures are logged and skipped; the method never raises
        unless ``pdfplumber`` cannot open the file at all.

        Returns
        -------
        str
            Full extracted text (may be empty if all pages failed).

        Raises
        ------
        AdapterError
            If pdfplumber cannot open the PDF file.
        """
        try:
            import pdfplumber
        except ImportError as exc:
            raise AdapterError(
                "pdfplumber is not installed. Run: pip install pdfplumber",
                source=self.source_name,
                cause=exc,
            ) from exc

        try:
            pdf = pdfplumber.open(str(self.path))
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(
                f"Cannot open PDF: {self.path} — {exc}",
                source=self.source_name,
                cause=exc,
            ) from exc

        page_texts: list[str] = []
        with pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                try:
                    text = page.extract_text() or ""
                    page_texts.append(text)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to extract text from page %d of %s: %s",
                        page_num, self.path, exc,
                    )

        return "\n".join(page_texts)

    @staticmethod
    def _build_provenance(
        field: str,
        source_path: str,
        raw_value: Optional[str],
        method: str,
        confidence: float = 0.75,
    ) -> ProvenanceRecord:
        """Construct a ProvenanceRecord for a résumé-extracted field."""
        return ProvenanceRecord(
            field=field,
            source=source_path,
            raw_value=raw_value,
            confidence=confidence,
            extracted_at=datetime.now(UTC),
            normalised=False,
            method=method,
        )

    # ------------------------------------------------------------------
    # SourceAdapter interface
    # ------------------------------------------------------------------

    def validate_source(self) -> None:
        """
        Validate that the résumé PDF exists and can be opened by pdfplumber.

        Raises
        ------
        AdapterError
            * File does not exist.
            * File extension is not ``.pdf``.
            * pdfplumber cannot open the file (corrupt / encrypted PDF).
        """
        if not self.path.exists():
            raise AdapterError(
                f"Resume PDF not found: {self.path}",
                source=self.source_name,
            )
        if not self.path.is_file():
            raise AdapterError(
                f"Resume path is not a file: {self.path}",
                source=self.source_name,
            )
        if self.path.suffix.lower() != ".pdf":
            raise AdapterError(
                f"Expected a .pdf file, got: {self.path.suffix!r}",
                source=self.source_name,
            )
        # Lightweight open check.
        try:
            import pdfplumber
            with pdfplumber.open(str(self.path)):
                pass
        except ImportError as exc:
            raise AdapterError(
                "pdfplumber is not installed.",
                source=self.source_name,
                cause=exc,
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(
                f"Cannot open PDF (possibly corrupt or encrypted): {self.path}",
                source=self.source_name,
                cause=exc,
            ) from exc

    def parse(self) -> CandidateProfile:
        """
        Extract candidate data from the résumé PDF.

        Extraction flow
        ---------------
        1. Extract full text via ``pdfplumber`` (page-level faults skipped).
        2. Run regex extractors for emails, phones, and links.
        3. Detect named sections (EXPERIENCE, EDUCATION, SKILLS, …).
        4. Apply name heuristic on header lines.
        5. Extract skills against the taxonomy.
        6. Parse experience and education blocks.
        7. Build ProvenanceRecord entries for all extracted fields.
        8. Construct and return ``CandidateProfile``.

        Returns
        -------
        CandidateProfile
            Canonical profile.  May be sparsely populated if the PDF yields
            little structured text.

        Raises
        ------
        AdapterError
            Only if ``pdfplumber`` cannot open the file at all.
        """
        source_path = self.path.name
        provenance: list[ProvenanceRecord] = []

        # Step 1: Extract raw text.
        full_text = self._extract_text()
        lines = full_text.splitlines()

        # Step 2: Regex-based contact extraction.
        emails = extract_emails(full_text)
        phones = extract_phones(full_text)
        link_map = extract_links(full_text)

        for i, email in enumerate(emails):
            provenance.append(
                self._build_provenance(f"emails[{i}]", source_path, email, "regex")
            )
        for i, phone in enumerate(phones):
            provenance.append(
                self._build_provenance(f"phones[{i}]", source_path, phone, "regex")
            )

        # Step 3: Section detection.
        sections = detect_sections(lines)

        # Step 4: Name heuristic.
        header_lines = sections.get("header", [])
        full_name = _extract_name_heuristic(header_lines)
        if full_name:
            provenance.append(
                self._build_provenance(
                    "full_name", source_path, full_name, "header_heuristic", confidence=0.65
                )
            )
            
        headline = _extract_headline_heuristic(header_lines, full_name)
        if headline:
            provenance.append(
                self._build_provenance(
                    "headline", source_path, headline, "headline_heuristic", confidence=0.65
                )
            )
            
        location_city = _extract_location_heuristic(header_lines)
        location = None
        if location_city:
            from src.models import Location
            location = Location(city=location_city, raw=location_city)
            provenance.append(
                self._build_provenance(
                    "location.city", source_path, location_city, "location_heuristic", confidence=0.75
                )
            )

        # Step 5: Skills extraction.
        taxonomy = self._get_taxonomy()
        # Use the full text for skill detection; also cross-check skills section.
        skills_text = full_text
        if "skills" in sections:
            skills_text = "\n".join(sections["skills"]) + "\n" + full_text
        skill_names = extract_skills(skills_text, taxonomy)
        skills: list[Skill] = []
        for sname in skill_names:
            skills.append(Skill(name=sname, sources=["resume"]))
            provenance.append(
                self._build_provenance(
                    f"skills[{len(skills)-1}].name", source_path, sname, "taxonomy_match"
                )
            )

        # Step 6a: Experience parsing.
        exp_lines = sections.get("experience", [])
        experience = parse_experience_section(exp_lines)
        for i, exp in enumerate(experience):
            provenance.append(
                self._build_provenance(
                    f"experience[{i}]", source_path, exp.title, "section_keyword"
                )
            )

        # Step 6b: Education parsing.
        edu_lines = sections.get("education", [])
        education = parse_education_section(edu_lines)
        for i, edu in enumerate(education):
            provenance.append(
                self._build_provenance(
                    f"education[{i}]", source_path, edu.institution, "section_keyword"
                )
            )

        # Step 7: Build links list.
        from src.models import Links
        links_obj = Links()
        all_link_urls = link_map.get("linkedin", []) + link_map.get("github", [])
        for i, raw_url in enumerate(all_link_urls):
            try:
                validated = str(HttpUrl(raw_url))
                link_type = "linkedin" if "linkedin" in raw_url else "github"
                setattr(links_obj, link_type, validated)
                provenance.append(
                    self._build_provenance(
                        f"links.{link_type}", source_path, raw_url, f"regex_{link_type}"
                    )
                )
            except ValidationError:
                logger.debug("Dropping invalid link from resume: %r", raw_url)

        # Step 8: Construct and return profile.
        try:
            profile = CandidateProfile(
                full_name=full_name,
                headline=headline,
                emails=emails,
                phones=phones,
                location=location,
                skills=skills,
                experience=experience,
                education=education,
                links=links_obj,
                provenance=provenance,
            )
        except ValidationError as exc:
            raise AdapterError(
                f"CandidateProfile construction failed for resume {self.path}: {exc}",
                source=self.source_name,
                cause=exc,
            ) from exc

        logger.info(
            "ResumeAdapter parsed profile for %r from %s (%d skills, %d experience, %d education)",
            profile.full_name,
            self.path,
            len(profile.skills),
            len(profile.experience),
            len(profile.education),
        )
        return profile
