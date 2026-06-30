"""
MergeEngine — deterministic, explainable multi-source profile consolidation.

This module implements the core merge logic for Phase A.  It takes two
:class:`~src.models.CandidateProfile` objects (typically one from an ATS
adapter and one from a résumé adapter) and produces a single authoritative
:class:`~src.models.CandidateProfile` along with a full audit log of every
decision made.

Design principles
-----------------
* **Deterministic**: given the same two inputs, the output is always identical.
* **Explainable**: every non-trivial choice is recorded as a
  :class:`~src.merger.models.MergeDecision`.
* **Traceable**: all provenance records from both inputs are preserved.
* **Robust**: ``None``, empty lists, and missing fields never cause crashes.
* **No ML**: only rule-based, priority-based, and set-theoretic operations.

Merge rules at a glance
-----------------------
+------------------+----------------------------------------------+
| Field            | Strategy                                     |
+==================+==============================================+
| full_name        | resume > ats (priority)                      |
+------------------+----------------------------------------------+
| headline         | resume > ats (priority)                      |
+------------------+----------------------------------------------+
| emails           | union, case-insensitive dedup                |
+------------------+----------------------------------------------+
| phones           | union, digit-normalised dedup                |
+------------------+----------------------------------------------+
| links            | per-platform: non-null wins; others unioned  |
+------------------+----------------------------------------------+
| location         | field-by-field; resume wins on conflict      |
+------------------+----------------------------------------------+
| skills           | union by canonical name (case-insensitive)   |
+------------------+----------------------------------------------+
| experience       | union; dedup on company+title+start_year     |
+------------------+----------------------------------------------+
| education        | union; dedup on institution+degree+end_year  |
+------------------+----------------------------------------------+
| provenance       | full union — never discard                   |
+------------------+----------------------------------------------+
| candidate_id     | resume > ats; auto-generate if both absent   |
+------------------+----------------------------------------------+
| years_experience | max(a, b)                                    |
+------------------+----------------------------------------------+
"""

from __future__ import annotations

import re
import logging
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import HttpUrl

from src.models import (
    CandidateProfile,
    Education,
    EducationDegree,
    Experience,
    Location,
    ProvenanceRecord,
    Skill,
)
from src.merger.models import MergeDecision, MergeReason, MergeResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_email(email: str) -> str:
    """Return email lowercased and stripped."""
    return email.strip().lower()


def _digits_only(phone: str) -> str:
    """Return only the digit characters from ``phone`` for deduplication."""
    return re.sub(r"\D", "", phone)


def _infer_source_label(profile: CandidateProfile, default: str) -> str:
    """
    Infer the human-readable source label from the profile's provenance.

    Looks at the first provenance record's ``source`` field; falls back to
    ``default`` if provenance is empty.
    """
    if profile.provenance:
        return profile.provenance[0].source
    return default


def _str_or_none(v: Any) -> Optional[str]:
    """Convert to stripped string or return ``None``."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


# ---------------------------------------------------------------------------
# MergeEngine
# ---------------------------------------------------------------------------

class MergeEngine:
    """
    Deterministic, rule-based engine for merging two ``CandidateProfile``
    objects into a single authoritative profile.

    The engine assumes both profiles represent **the same candidate** —
    cross-candidate matching is out of scope.

    Parameters
    ----------
    profile_a_label:
        Human-readable label for the first input profile (default ``"ats"``).
        Used in decision records and log messages.
    profile_b_label:
        Human-readable label for the second input profile
        (default ``"resume"``).

    Usage
    -----
    ::

        engine = MergeEngine()
        result: MergeResult = engine.merge(ats_profile, resume_profile)

        print(result.merged_profile.full_name)
        print(result.conflict_count)

        for decision in result.merge_decisions:
            print(decision)
    """

    def __init__(
        self,
        profile_a_label: str = "ats",
        profile_b_label: str = "resume",
    ) -> None:
        self._label_a = profile_a_label
        self._label_b = profile_b_label

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def merge(
        self,
        profile_a: CandidateProfile,
        profile_b: CandidateProfile,
    ) -> MergeResult:
        """
        Merge ``profile_a`` (ATS) and ``profile_b`` (résumé) into one.

        The merge is **profile_b-priority** for scalar string fields, meaning
        the résumé value is preferred over the ATS value on conflict.  Other
        fields (emails, phones, skills, etc.) follow set-union semantics with
        field-specific deduplication keys.

        Parameters
        ----------
        profile_a:
            First input profile (conventionally the ATS profile).
        profile_b:
            Second input profile (conventionally the résumé profile).

        Returns
        -------
        MergeResult
            Contains the merged ``CandidateProfile`` and the full decision log.

        Notes
        -----
        * Neither input profile is mutated.
        * If both inputs are empty, an empty profile is returned — no crash.
        """
        decisions: list[MergeDecision] = []

        # Infer source labels from provenance where possible.
        label_a = _infer_source_label(profile_a, self._label_a)
        label_b = _infer_source_label(profile_b, self._label_b)

        def _decision(
            field: str,
            chosen: Any,
            discarded: Any,
            reason: MergeReason,
            notes: Optional[str] = None,
        ) -> None:
            decisions.append(
                MergeDecision(
                    field_name=field,
                    chosen_value=chosen,
                    discarded_value=discarded,
                    reason=reason,
                    source_a_label=label_a,
                    source_b_label=label_b,
                    notes=notes,
                )
            )

        # ── scalar fields ────────────────────────────────────────────────────
        candidate_id   = self._merge_candidate_id(profile_a, profile_b, _decision)
        full_name      = self._merge_name(profile_a, profile_b, _decision)
        headline       = self._merge_headline(profile_a, profile_b, _decision)
        years_exp      = self._merge_years_experience(profile_a, profile_b, _decision)

        # ── list / set fields ────────────────────────────────────────────────
        emails         = self._merge_emails(profile_a, profile_b, _decision)
        phones         = self._merge_phones(profile_a, profile_b, _decision)
        links          = self._merge_links(profile_a, profile_b, _decision)
        location       = self._merge_location(profile_a, profile_b, _decision)
        skills         = self._merge_skills(profile_a, profile_b, _decision)
        experience     = self._merge_experience(profile_a, profile_b, _decision)
        education      = self._merge_education(profile_a, profile_b, _decision)

        # ── provenance (full union — never discard) ──────────────────────────
        provenance     = self._merge_provenance(profile_a, profile_b)

        now = datetime.now(UTC)
        merged = CandidateProfile(
            candidate_id=candidate_id,
            full_name=full_name,
            headline=headline,
            years_experience=years_exp,
            emails=emails,
            phones=phones,
            links=links,
            location=location,
            skills=skills,
            experience=experience,
            education=education,
            provenance=provenance,
            created_at=min(profile_a.created_at, profile_b.created_at),
            updated_at=now,
        )

        logger.info(
            "Merged profiles: name=%r | skills=%d | experience=%d | "
            "education=%d | conflicts=%d",
            merged.full_name,
            len(merged.skills),
            len(merged.experience),
            len(merged.education),
            sum(1 for d in decisions if d.discarded_value is not None),
        )

        return MergeResult(
            merged_profile=merged,
            merge_decisions=decisions,
            profile_a_source=label_a,
            profile_b_source=label_b,
        )

    # -----------------------------------------------------------------------
    # candidate_id
    # -----------------------------------------------------------------------

    def _merge_candidate_id(
        self,
        a: CandidateProfile,
        b: CandidateProfile,
        record: Any,
    ) -> UUID:
        """
        Select a ``candidate_id``.

        Priority: ATS (profile_a).
        """
        if a.candidate_id:
            return a.candidate_id
        if b.candidate_id:
            return b.candidate_id
        return uuid4()

    # -----------------------------------------------------------------------
    # full_name
    # -----------------------------------------------------------------------

    def _merge_name(
        self,
        a: CandidateProfile,
        b: CandidateProfile,
        record: Any,
    ) -> Optional[str]:
        """
        Resolve ``full_name``.

        Priority: résumé (b) > ATS (a).

        Résumés contain the candidate-authored form of their name, which is
        generally more accurate than the ATS-stored version.
        """
        name_a = _str_or_none(a.full_name)
        name_b = _str_or_none(b.full_name)

        if name_b and name_a:
            if name_b.lower() != name_a.lower():
                record(
                    "full_name",
                    name_b,
                    name_a,
                    MergeReason.RESUME_PRIORITY,
                )
            else:
                record(
                    "full_name",
                    name_b,
                    None,
                    MergeReason.DEDUPLICATION,
                    notes="Identical names — kept once.",
                )
            return name_b

        if name_b:
            record("full_name", name_b, None, MergeReason.ONLY_VALUE)
            return name_b
        if name_a:
            record("full_name", name_a, None, MergeReason.ONLY_VALUE)
            return name_a

        record("full_name", None, None, MergeReason.NO_DATA)
        return None

    # -----------------------------------------------------------------------
    # headline
    # -----------------------------------------------------------------------

    def _merge_headline(
        self,
        a: CandidateProfile,
        b: CandidateProfile,
        record: Any,
    ) -> Optional[str]:
        """
        Resolve ``headline``.

        Priority: résumé (b) > ATS (a).
        """
        hl_a = _str_or_none(a.headline)
        hl_b = _str_or_none(b.headline)

        if hl_b and hl_a:
            if hl_b.lower() != hl_a.lower():
                record("headline", hl_b, hl_a, MergeReason.RESUME_PRIORITY)
            else:
                record("headline", hl_b, None, MergeReason.DEDUPLICATION)
            return hl_b

        chosen = hl_b or hl_a
        reason = MergeReason.ONLY_VALUE if chosen else MergeReason.NO_DATA
        record("headline", chosen, None, reason)
        return chosen

    # -----------------------------------------------------------------------
    # years_experience
    # -----------------------------------------------------------------------

    def _merge_years_experience(
        self,
        a: CandidateProfile,
        b: CandidateProfile,
        record: Any,
    ) -> Optional[float]:
        """
        Resolve ``years_experience`` by selecting the **larger** value.

        Résumés typically contain a more complete work history, so they tend
        to yield a higher (more accurate) figure.  Choosing the larger value
        is a conservative, candidate-friendly heuristic.
        """
        yr_a = a.years_experience
        yr_b = b.years_experience

        if yr_a is not None and yr_b is not None:
            chosen, discarded = (yr_b, yr_a) if yr_b >= yr_a else (yr_a, yr_b)
            record(
                "years_experience",
                chosen,
                discarded if discarded != chosen else None,
                MergeReason.LARGER_VALUE,
            )
            return chosen

        chosen = yr_b if yr_b is not None else yr_a
        reason = MergeReason.ONLY_VALUE if chosen is not None else MergeReason.NO_DATA
        record("years_experience", chosen, None, reason)
        return chosen

    # -----------------------------------------------------------------------
    # emails
    # -----------------------------------------------------------------------

    def _merge_emails(
        self,
        a: CandidateProfile,
        b: CandidateProfile,
        record: Any,
    ) -> list[str]:
        """
        Union emails from both profiles, deduplicating case-insensitively.

        Ordering: profile_a emails first, then any new emails from profile_b.
        The first occurrence (lowercased) is kept; duplicates are dropped.
        """
        seen: set[str] = set()
        merged: list[str] = []

        for email in list(a.emails) + list(b.emails):
            key = _normalise_email(str(email))
            if key not in seen:
                seen.add(key)
                merged.append(key)

        record(
            "emails",
            merged,
            None,
            MergeReason.UNION if merged else MergeReason.NO_DATA,
            notes=f"{len(merged)} unique addresses after dedup.",
        )
        return merged

    # -----------------------------------------------------------------------
    # phones
    # -----------------------------------------------------------------------

    def _merge_phones(
        self,
        a: CandidateProfile,
        b: CandidateProfile,
        record: Any,
    ) -> list[str]:
        """
        Union phone numbers, deduplicating by digit-only form.

        The first encountered representation of a number is preserved
        (formatting is not yet normalised — that is Phase 3's job).
        """
        seen_digits: set[str] = set()
        merged: list[str] = []

        for phone in list(a.phones) + list(b.phones):
            key = _digits_only(str(phone))
            if key and key not in seen_digits:
                seen_digits.add(key)
                merged.append(str(phone))

        record(
            "phones",
            merged,
            None,
            MergeReason.UNION if merged else MergeReason.NO_DATA,
            notes=f"{len(merged)} unique phones after digit dedup.",
        )
        return merged

    # -----------------------------------------------------------------------
    # links
    # -----------------------------------------------------------------------

    def _merge_links(
        self,
        a: CandidateProfile,
        b: CandidateProfile,
        record: Any,
    ) -> Any:  # Returns Links object
        """
        Merge Links with per-platform semantics.
        Résumé wins on conflict.
        """
        from src.models import Links
        merged = Links()
        
        links_a = a.links
        links_b = b.links
        
        for platform in ["linkedin", "github", "portfolio"]:
            val_a = getattr(links_a, platform)
            val_b = getattr(links_b, platform)
            
            if val_b and val_a:
                if val_b != val_a:
                    record(f"links.{platform}", val_b, val_a, MergeReason.RESUME_PRIORITY)
                setattr(merged, platform, val_b)
            elif val_b:
                record(f"links.{platform}", val_b, None, MergeReason.ONLY_VALUE)
                setattr(merged, platform, val_b)
            elif val_a:
                record(f"links.{platform}", val_a, None, MergeReason.ONLY_VALUE)
                setattr(merged, platform, val_a)
                
        # Union other links
        seen_other: set[str] = set()
        for url in list(links_a.other) + list(links_b.other):
            if url not in seen_other:
                seen_other.add(url)
                merged.other.append(url)
                
        if merged.other:
            record("links.other", merged.other, None, MergeReason.UNION)
            
        return merged

    # -----------------------------------------------------------------------
    # location
    # -----------------------------------------------------------------------

    def _merge_location(
        self,
        a: CandidateProfile,
        b: CandidateProfile,
        record: Any,
    ) -> Optional[Location]:
        """
        Merge ``location`` field-by-field.

        For each sub-field (city, state, country, postal_code, raw):
        * If only one profile has it → use it.
        * If both have it and they differ → résumé (profile_b) wins.
        * If both have it and they agree → keep it.
        """
        loc_a = a.location
        loc_b = b.location

        if loc_a is None and loc_b is None:
            record("location", None, None, MergeReason.NO_DATA)
            return None
        if loc_a is None:
            record("location", loc_b, None, MergeReason.ONLY_VALUE)
            return loc_b
        if loc_b is None:
            record("location", loc_a, None, MergeReason.ONLY_VALUE)
            return loc_a

        # Both exist — merge field by field.
        def _pick(field: str, val_a: Optional[str], val_b: Optional[str]) -> Optional[str]:
            if val_b and val_a and val_b != val_a:
                record(
                    f"location.{field}",
                    val_b,
                    val_a,
                    MergeReason.RESUME_PRIORITY,
                )
                return val_b
            return val_b or val_a

        city        = _pick("city",        loc_a.city,        loc_b.city)
        region      = _pick("region",      loc_a.region,      loc_b.region)
        country     = _pick("country",     loc_a.country,     loc_b.country)
        postal_code = _pick("postal_code", loc_a.postal_code, loc_b.postal_code)
        raw         = _pick("raw",         loc_a.raw,         loc_b.raw)

        merged = Location(
            city=city,
            region=region,
            country=country,
            postal_code=postal_code,
            raw=raw,
        )
        record(
            "location",
            merged,
            None,
            MergeReason.FIELD_LEVEL_MERGE,
            notes="Sub-fields merged independently; resume wins on conflict.",
        )
        return merged

    # -----------------------------------------------------------------------
    # skills
    # -----------------------------------------------------------------------

    @staticmethod
    def _skill_key(skill: Skill) -> str:
        """Canonical dedup key: lowercased skill name, stripped."""
        return skill.name.strip().lower()

    def _merge_skills(
        self,
        a: CandidateProfile,
        b: CandidateProfile,
        record: Any,
    ) -> list[Skill]:
        """
        Union skills from both profiles, deduplicating by canonical name.

        When the same skill appears in both sources:
        * The skill from profile_b (résumé) is preferred (it may carry a
          higher ``level`` or ``years_of_experience``).
        * The ``source`` field is updated to ``"merged"`` to indicate
          multi-source provenance.

        No fuzzy matching is performed — skill names must match exactly
        after lowercasing and stripping.
        """
        seen: dict[str, Skill] = {}
        merged_source_keys: set[str] = set()  # keys seen in both

        # First pass: all skills from profile_a.
        for skill in a.skills:
            key = self._skill_key(skill)
            seen[key] = skill

        # Second pass: skills from profile_b override; track merges.
        for skill in b.skills:
            key = self._skill_key(skill)
            if key in seen:
                merged_source_keys.add(key)
                # Replace with résumé version (may have richer metadata).
                seen[key] = Skill(
                    name=skill.name,
                    confidence=skill.confidence,
                    sources=list(set(skill.sources + seen[key].sources)),
                    level=skill.level,
                    years_of_experience=skill.years_of_experience
                        or seen[key].years_of_experience,
                    last_used_year=skill.last_used_year
                        or seen[key].last_used_year,
                )
            else:
                seen[key] = skill

        merged_skills = list(seen.values())
        
        # Recompute confidence based on deterministic source rules
        merged_skills_final = []
        for skill in merged_skills:
            if "ats" in skill.sources and "resume" in skill.sources:
                new_conf = 1.00
            elif "ats" in skill.sources:
                new_conf = 0.90
            elif "resume" in skill.sources:
                new_conf = 0.80
            else:
                new_conf = 0.50
            merged_skills_final.append(skill.model_copy(update={"confidence": new_conf}))

        record(
            "skills",
            [s.name for s in merged_skills_final],
            None,
            MergeReason.UNION,
            notes=(
                f"{len(merged_skills_final)} unique skills; "
                f"{len(merged_source_keys)} appeared in both sources."
            ),
        )
        return merged_skills_final

    # -----------------------------------------------------------------------
    # experience
    # -----------------------------------------------------------------------

    @staticmethod
    def _experience_key(exp: Experience) -> tuple[str, str, str]:
        """
        Deduplication key: (lowercased company, lowercased title, start year).

        Only deduplicate if all three components match — otherwise keep both.
        """
        company    = (exp.company or "").strip().lower()
        title      = (exp.title or "").strip().lower()
        start_year = exp.start[:4] if exp.start else ""
        return (company, title, start_year)

    def _merge_experience(
        self,
        a: CandidateProfile,
        b: CandidateProfile,
        record: Any,
    ) -> list[Experience]:
        """
        Union experience lists, deduplicating on company + title + start_year.

        When two entries have the same key:
        * The résumé entry (profile_b) wins — it tends to have richer
          descriptions.
        * All other non-matching entries from both profiles are kept.

        The result is sorted chronologically (descending) by ``start_date``
        so the most recent role appears first.
        """
        seen: dict[tuple[str, str, str], Experience] = {}
        dedup_count = 0

        # Profile_a entries first.
        for exp in a.experience:
            key = self._experience_key(exp)
            seen[key] = exp

        # Profile_b (résumé) entries override duplicates.
        for exp in b.experience:
            key = self._experience_key(exp)
            if key in seen and seen[key] != exp:
                dedup_count += 1
            seen[key] = exp  # Always prefer résumé.

        # Sort descending by start (None → oldest).
        def _sort_key(exp: Experience):
            return exp.start or ""

        merged = sorted(seen.values(), key=_sort_key, reverse=True)

        record(
            "experience",
            [f"{e.title} @ {e.company}" for e in merged],
            None,
            MergeReason.UNION,
            notes=f"{len(merged)} entries; {dedup_count} deduplicated.",
        )
        return merged

    # -----------------------------------------------------------------------
    # education
    # -----------------------------------------------------------------------

    @staticmethod
    def _education_key(edu: Education) -> tuple[str, str, str]:
        """
        Deduplication key: (lowercased institution, degree value, end year).
        """
        institution = (edu.institution or "").strip().lower()
        degree      = edu.degree.value
        end_year    = str(edu.end_year) if edu.end_year else ""
        return (institution, degree, end_year)

    def _merge_education(
        self,
        a: CandidateProfile,
        b: CandidateProfile,
        record: Any,
    ) -> list[Education]:
        """
        Union education lists, deduplicating on institution + degree + end_year.

        When two entries have the same key, the résumé entry wins (it often
        carries GPA or field-of-study data that the ATS lacks).
        """
        seen: dict[tuple[str, str, str], Education] = {}
        dedup_count = 0

        for edu in a.education:
            key = self._education_key(edu)
            seen[key] = edu

        for edu in b.education:
            key = self._education_key(edu)
            if key in seen and seen[key] != edu:
                dedup_count += 1
            seen[key] = edu  # Résumé wins.

        # Sort descending by end_year.
        def _sort_key(edu: Education):
            return str(edu.end_year) if edu.end_year else ""

        merged = sorted(seen.values(), key=_sort_key, reverse=True)

        record(
            "education",
            [f"{e.degree.value} @ {e.institution}" for e in merged],
            None,
            MergeReason.UNION,
            notes=f"{len(merged)} entries; {dedup_count} deduplicated.",
        )
        return merged

    # -----------------------------------------------------------------------
    # provenance
    # -----------------------------------------------------------------------

    @staticmethod
    def _merge_provenance(
        a: CandidateProfile,
        b: CandidateProfile,
    ) -> list[ProvenanceRecord]:
        """
        Combine all provenance records from both profiles.

        Provenance is **never discarded** — the full audit trail from every
        source is preserved so downstream tools can trace any field back to
        its origin.
        """
        return list(a.provenance) + list(b.provenance)
