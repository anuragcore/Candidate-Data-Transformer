"""
ATS (Applicant Tracking System) adapter — Phase 2 implementation.

Reads a structured ATS JSON file and maps its fields to the canonical
:class:`~src.models.CandidateProfile` schema.

Field mapping strategy
----------------------
Multiple source-side aliases are tried for each canonical field so the
adapter can handle JSON from different ATS vendors without modification.
The first alias that yields a non-null value wins.

Error handling contract
-----------------------
* **Unrecoverable** (raises ``AdapterError``): file missing, file unreadable,
  file is not valid JSON.
* **Recoverable** (skips / uses default): missing key, wrong value type,
  invalid email format, invalid URL, out-of-range numeric value.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import HttpUrl, ValidationError

from src.adapters.base import AdapterError, SourceAdapter
from src.models import (
    CandidateProfile,
    Education,
    EducationDegree,
    Experience,
    Location,
    ProvenanceRecord,
    Skill,
)
from src.utils.date_parser import is_present, parse_date_string
from src.utils.text_extractors import extract_emails

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field alias maps — ordered by preference (first match wins)
# ---------------------------------------------------------------------------

_NAME_KEYS: list[str] = ["candidateName", "fullName", "name", "full_name"]
_EMAIL_KEYS: list[str] = ["primaryEmail", "email", "emailAddress", "emails"]
_PHONE_KEYS: list[str] = ["mobile", "phone", "phoneNumber", "mobileNumber", "phones"]
_HEADLINE_KEYS: list[str] = ["headline", "summary", "title", "jobTitle", "currentTitle"]
_YEARS_EXP_KEYS: list[str] = ["yearsExperience", "totalExperience", "years_experience"]
_LOCATION_KEYS: list[str] = ["location", "address", "city", "currentLocation"]
_LINKEDIN_KEYS: list[str] = ["linkedinUrl", "linkedin", "linkedIn", "linkedinProfile"]
_GITHUB_KEYS: list[str] = ["githubUrl", "github", "githubProfile"]
_SKILLS_KEYS: list[str] = ["skills", "skillSet", "technicalSkills"]
_EXPERIENCE_KEYS: list[str] = ["experience", "workHistory", "positions", "jobs"]
_EDUCATION_KEYS: list[str] = ["education", "educationHistory", "qualifications"]


# ---------------------------------------------------------------------------
# Helper utilities (private, ATS-specific)
# ---------------------------------------------------------------------------

def _first(data: dict[str, Any], keys: list[str]) -> Any:
    """Return the value of the first key found in ``data``, or ``None``."""
    for key in keys:
        val = data.get(key)
        if val is not None:
            return val
    return None


def _as_str(val: Any) -> Optional[str]:
    """Coerce ``val`` to a stripped string, or ``None`` if empty/None."""
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _as_float(val: Any) -> Optional[float]:
    """Coerce ``val`` to a float, or ``None`` on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _as_str_list(val: Any) -> list[str]:
    """
    Coerce ``val`` to a list of strings.

    Handles: ``list``, comma-separated ``str``, single ``str``.
    """
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v).strip() for v in val if v is not None and str(v).strip()]
    if isinstance(val, str):
        return [s.strip() for s in val.split(",") if s.strip()]
    return [str(val).strip()] if str(val).strip() else []


def _safe_http_url(raw: Optional[str]) -> Optional[str]:
    """
    Validate that ``raw`` is a parseable HTTP URL.

    Returns the URL string if valid, ``None`` otherwise.  Does NOT raise.
    """
    if not raw:
        return None
    raw = raw.strip()
    # Prepend scheme if missing so Pydantic can validate.
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        url = HttpUrl(raw)
        return str(url)
    except ValidationError:
        logger.debug("Skipping invalid URL: %r", raw)
        return None


def _build_provenance(
    field: str,
    source_path: str,
    raw_value: Optional[str],
    method: str = "json_key_mapping",
) -> ProvenanceRecord:
    """Construct a lightweight ProvenanceRecord for a mapped ATS field."""
    return ProvenanceRecord(
        field=field,
        source=source_path,
        raw_value=raw_value,
        confidence=0.95,  # ATS structured data gets high baseline confidence.
        extracted_at=datetime.now(UTC),
        normalised=False,
        method=method,
    )


# ---------------------------------------------------------------------------
# Experience / Education sub-parsers
# ---------------------------------------------------------------------------

def _parse_experience_entry(entry: dict[str, Any], source_path: str) -> Optional[Experience]:
    """Map a single ATS experience dict to an ``Experience`` model."""
    if not isinstance(entry, dict):
        return None
    try:
        start_raw = _as_str(_first(entry, ["startDate", "start_date", "from"]))
        end_raw = _as_str(_first(entry, ["endDate", "end_date", "to", "until"]))
        is_current = bool(entry.get("isCurrent", entry.get("is_current", False)))
        if end_raw and is_present(end_raw):
            is_current = True
            end_raw = None

        location_raw = _as_str(_first(entry, ["location", "city", "place"]))

        return Experience(
            title=_as_str(_first(entry, ["title", "jobTitle", "position", "role"])),
            company=_as_str(_first(entry, ["company", "employer", "organisation", "organization"])),
            start=start_raw,
            end=end_raw,
            summary=_as_str(_first(entry, ["description", "summary", "responsibilities"])),
            location=Location(raw=location_raw) if location_raw else None,
            start_date=parse_date_string(start_raw) if start_raw else None,
            end_date=parse_date_string(end_raw) if end_raw else None,
            is_current=is_current,
            skills_used=_as_str_list(_first(entry, ["skillsUsed", "skills_used", "skills", "technologies"])),
            source="ats",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skipping malformed experience entry: %s", exc)
        return None


def _parse_education_entry(entry: dict[str, Any], source_path: str) -> Optional[Education]:
    """Map a single ATS education dict to an ``Education`` model."""
    if not isinstance(entry, dict):
        return None
    try:
        degree_raw = _as_str(_first(entry, ["degree", "qualification", "level"]))
        degree_enum = EducationDegree.UNKNOWN
        if degree_raw:
            degree_lower = degree_raw.lower()
            mapping = {
                "phd": EducationDegree.DOCTORATE,
                "doctorate": EducationDegree.DOCTORATE,
                "master": EducationDegree.MASTER,
                "mba": EducationDegree.MASTER,
                "bachelor": EducationDegree.BACHELOR,
                "associate": EducationDegree.ASSOCIATE,
                "high school": EducationDegree.HIGH_SCHOOL,
                "certificate": EducationDegree.CERTIFICATE,
                "bootcamp": EducationDegree.BOOTCAMP,
            }
            for kw, enum_val in mapping.items():
                if kw in degree_lower:
                    degree_enum = enum_val
                    break

        start_raw = _as_str(_first(entry, ["startDate", "start_date", "from"]))
        end_raw = _as_str(_first(entry, ["endDate", "end_date", "graduationDate", "to"]))
        is_completed = not (end_raw and is_present(end_raw))

        return Education(
            institution=_as_str(_first(entry, ["institution", "school", "university", "college"])),
            degree=degree_enum,
            field=_as_str(_first(entry, ["fieldOfStudy", "field_of_study", "major", "subject"])),
            end_year=end_raw,
            start_date=parse_date_string(start_raw) if start_raw else None,
            end_date=parse_date_string(end_raw) if (end_raw and not is_present(end_raw)) else None,
            gpa=_as_float(_first(entry, ["gpa", "grade", "cgpa"])),
            is_completed=is_completed,
            source="ats",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skipping malformed education entry: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main adapter class
# ---------------------------------------------------------------------------

class ATSAdapter(SourceAdapter):
    """
    Adapter for structured ATS JSON exports.

    Reads a JSON file from ``path``, applies field-alias resolution to map
    ATS-vendor-specific keys to the canonical :class:`~src.models.CandidateProfile`
    schema, and returns a fully populated profile.

    Parameters
    ----------
    path:
        Filesystem path to the ATS JSON input file.

    Example
    -------
    ::

        adapter = ATSAdapter(path=Path("inputs/candidate_ats.json"))
        adapter.validate_source()
        profile = adapter.parse()
    """

    source_name: str = "ats"

    def __init__(self, path: Path) -> None:
        """
        Initialise the ATS adapter.

        Parameters
        ----------
        path:
            Path to the ATS JSON file.  Converted to ``Path`` if a string
            is provided.
        """
        self.path = Path(path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_json(self) -> dict[str, Any]:
        """
        Read and parse the JSON file.

        Returns
        -------
        dict[str, Any]
            Parsed JSON payload.

        Raises
        ------
        AdapterError
            If the file cannot be read or is not valid JSON.
        """
        try:
            raw_text = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise AdapterError(
                f"Cannot read ATS file: {self.path}",
                source=self.source_name,
                cause=exc,
            ) from exc

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise AdapterError(
                f"ATS file is not valid JSON: {self.path} — {exc}",
                source=self.source_name,
                cause=exc,
            ) from exc

        if not isinstance(data, dict):
            raise AdapterError(
                f"ATS JSON root must be an object (dict), got {type(data).__name__}",
                source=self.source_name,
            )

        return data

    # ------------------------------------------------------------------
    # SourceAdapter interface
    # ------------------------------------------------------------------

    def validate_source(self) -> None:
        """
        Validate that the ATS JSON file exists and is parseable.

        Raises
        ------
        AdapterError
            * File does not exist.
            * File is not readable.
            * File content is not valid JSON.
        """
        if not self.path.exists():
            raise AdapterError(
                f"ATS file not found: {self.path}",
                source=self.source_name,
            )
        if not self.path.is_file():
            raise AdapterError(
                f"ATS path is not a file: {self.path}",
                source=self.source_name,
            )
        # Lightweight parse check — raises AdapterError on bad JSON.
        self._load_json()

    def parse(self) -> CandidateProfile:
        """
        Parse the ATS JSON file and return a canonical ``CandidateProfile``.

        The method is **fault-tolerant** at the field level: individual
        missing or malformed values are skipped with a warning log rather
        than crashing the entire parse.

        Returns
        -------
        CandidateProfile
            Canonical profile populated from ATS data.  Fields absent from
            the source are left as ``None`` or empty lists.

        Raises
        ------
        AdapterError
            If the file is missing, unreadable, or not valid JSON.
        """
        data = self._load_json()
        source_path = self.path.name
        provenance: list[ProvenanceRecord] = []

        # ------------------------------------------------------------------
        # full_name
        # ------------------------------------------------------------------
        full_name = _as_str(_first(data, _NAME_KEYS))
        if full_name:
            provenance.append(_build_provenance("full_name", source_path, full_name))

        # ------------------------------------------------------------------
        # emails — validate each address; skip invalid ones
        # ------------------------------------------------------------------
        raw_emails = _first(data, _EMAIL_KEYS)
        email_candidates: list[str] = _as_str_list(raw_emails)
        # Also run regex extractor over any string values to catch embedded addresses.
        if isinstance(raw_emails, str):
            email_candidates = extract_emails(raw_emails) or email_candidates

        valid_emails: list[str] = []
        for addr in email_candidates:
            try:
                # Use Pydantic to validate each address individually.
                from pydantic import TypeAdapter
                _email_validator = TypeAdapter(str)  # lightweight; real validation below
                # Simple format check via regex (full Pydantic check at model construction).
                import re as _re
                if _re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", addr):
                    valid_emails.append(addr.lower())
                    provenance.append(_build_provenance(f"emails[{len(valid_emails)-1}]", source_path, addr))
            except Exception:  # noqa: BLE001
                logger.debug("Skipping invalid email: %r", addr)

        # ------------------------------------------------------------------
        # phones
        # ------------------------------------------------------------------
        raw_phones = _first(data, _PHONE_KEYS)
        phones: list[str] = _as_str_list(raw_phones)
        for i, ph in enumerate(phones):
            provenance.append(_build_provenance(f"phones[{i}]", source_path, ph))

        # ------------------------------------------------------------------
        # headline
        # ------------------------------------------------------------------
        headline = _as_str(_first(data, _HEADLINE_KEYS))
        if headline:
            provenance.append(_build_provenance("headline", source_path, headline))

        # ------------------------------------------------------------------
        # years_experience
        # ------------------------------------------------------------------
        years_exp = _as_float(_first(data, _YEARS_EXP_KEYS))
        if years_exp is not None:
            provenance.append(_build_provenance("years_experience", source_path, str(years_exp)))

        # ------------------------------------------------------------------
        # location
        # ------------------------------------------------------------------
        location: Optional[Location] = None
        location_raw = _as_str(_first(data, _LOCATION_KEYS))
        if location_raw:
            location = Location(raw=location_raw)
            provenance.append(_build_provenance("location", source_path, location_raw))

        # ------------------------------------------------------------------
        # skills
        # ------------------------------------------------------------------
        raw_skills = _first(data, _SKILLS_KEYS)
        skill_names: list[str] = _as_str_list(raw_skills)
        skills: list[Skill] = []
        for sname in skill_names:
            if sname:
                skills.append(Skill(name=sname, sources=["ats"]))
                provenance.append(_build_provenance(f"skills[{len(skills)-1}].name", source_path, sname))

        # ------------------------------------------------------------------
        # links (LinkedIn, GitHub)
        # ------------------------------------------------------------------
        from src.models import Links
        links_obj = Links()
        for key_list, label in [(_LINKEDIN_KEYS, "linkedin"), (_GITHUB_KEYS, "github")]:
            raw_url = _as_str(_first(data, key_list))
            validated = _safe_http_url(raw_url)
            if validated:
                setattr(links_obj, label, validated)
                provenance.append(_build_provenance(f"links.{label}", source_path, raw_url))

        # ------------------------------------------------------------------
        # experience
        # ------------------------------------------------------------------
        raw_exp_list = _first(data, _EXPERIENCE_KEYS)
        experience_entries: list[Experience] = []
        if isinstance(raw_exp_list, list):
            for entry in raw_exp_list:
                parsed_exp = _parse_experience_entry(entry, source_path)
                if parsed_exp:
                    experience_entries.append(parsed_exp)
                    provenance.append(
                        _build_provenance(
                            f"experience[{len(experience_entries)-1}]",
                            source_path,
                            str(entry),
                        )
                    )

        # ------------------------------------------------------------------
        # education
        # ------------------------------------------------------------------
        raw_edu_list = _first(data, _EDUCATION_KEYS)
        education_entries: list[Education] = []
        if isinstance(raw_edu_list, list):
            for entry in raw_edu_list:
                parsed_edu = _parse_education_entry(entry, source_path)
                if parsed_edu:
                    education_entries.append(parsed_edu)
                    provenance.append(
                        _build_provenance(
                            f"education[{len(education_entries)-1}]",
                            source_path,
                            str(entry),
                        )
                    )

        # ------------------------------------------------------------------
        # Assemble and return CandidateProfile
        # ------------------------------------------------------------------
        try:
            profile = CandidateProfile(
                full_name=full_name,
                emails=valid_emails,
                phones=phones,
                location=location,
                headline=headline,
                years_experience=years_exp,
                skills=skills,
                links=links_obj,
                experience=experience_entries,
                education=education_entries,
                provenance=provenance,
            )
        except ValidationError as exc:
            raise AdapterError(
                f"CandidateProfile construction failed: {exc}",
                source=self.source_name,
                cause=exc,
            ) from exc

        logger.info(
            "ATSAdapter parsed profile for %r from %s",
            profile.full_name,
            self.path,
        )
        return profile
