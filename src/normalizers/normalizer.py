"""
Normalizer — field-level value standardisation engine.

The ``Normalizer`` is responsible for transforming the raw values extracted by
adapters into consistent, standardised forms. It operates **field by field**
on a single :class:`~src.models.CandidateProfile` and returns a new, normalised
copy.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import phonenumbers
from pydantic import EmailStr, HttpUrl

from src.models import (
    CandidateProfile,
    Location,
    Skill,
    Experience,
    Education,
    ProvenanceRecord,
)
from src.utils.date_parser import parse_date_string


class Normalizer:
    """
    Applies deterministic field-level normalisation rules to a ``CandidateProfile``.
    """

    def __init__(self, taxonomy_path: Optional[Path] = None) -> None:
        """
        Initialise the normalizer, optionally loading a skill taxonomy.
        """
        if taxonomy_path is None:
            taxonomy_path = Path("config/skill_taxonomy.json")
        self.taxonomy: dict[str, str] = {}
        if taxonomy_path.exists():
            try:
                raw_tax = json.loads(taxonomy_path.read_text(encoding="utf-8"))
                self.taxonomy = {k.lower(): str(v) for k, v in raw_tax.items()}
            except Exception:
                pass

    def normalize(self, profile: CandidateProfile) -> CandidateProfile:
        """
        Apply all normalisation rules to ``profile`` and return a clean copy.
        This operation is deterministic and idempotent.
        """
        # We work on a deep copy so we don't mutate the original profile.
        p = deepcopy(profile)

        # 1. Name Normalization
        if p.full_name is not None:
            new_name = self._normalize_name(p.full_name, title_case=True)
            if new_name != p.full_name:
                p.full_name = new_name
                self._add_provenance(p, "full_name", "name_normalization")

        # 2. Headline Normalization (same as name, collapse spaces)
        if p.headline is not None:
            new_headline = self._normalize_name(p.headline)
            if new_headline != p.headline:
                p.headline = new_headline
                self._add_provenance(p, "headline", "whitespace_normalization")

        # 3. Location Normalization
        if p.location is not None:
            new_loc, changed = self._normalize_location(p.location)
            if changed:
                p.location = new_loc
                self._add_provenance(p, "location", "location_normalization")

        # 4. Email Normalization & Deduplication
        new_emails = []
        emails_changed = False
        seen_emails: set[str] = set()
        for i, email in enumerate(p.emails):
            norm_email = self._normalize_email(str(email))
            if norm_email:
                if norm_email not in seen_emails:
                    seen_emails.add(norm_email)
                    new_emails.append(norm_email)
                if norm_email != str(email) or len(new_emails) - 1 != i:
                    emails_changed = True
            else:
                emails_changed = True

        if emails_changed:
            p.emails = new_emails  # type: ignore[assignment]
            self._add_provenance(p, "emails", "email_normalization")

        # 5. Phone Normalization & Deduplication
        new_phones = []
        phones_changed = False
        seen_phones: set[str] = set()
        for i, phone in enumerate(p.phones):
            norm_phone = self._normalize_phone(phone)
            if norm_phone:
                if norm_phone not in seen_phones:
                    seen_phones.add(norm_phone)
                    new_phones.append(norm_phone)
                if norm_phone != phone or len(new_phones) - 1 != i:
                    phones_changed = True
            else:
                phones_changed = True

        if phones_changed:
            p.phones = new_phones
            self._add_provenance(p, "phones", "e164_normalization")

        # 6. Link Normalization
        links_changed = False
        from src.models import Links
        new_links = Links()
        
        for field_name in ["linkedin", "github", "portfolio"]:
            val = getattr(p.links, field_name)
            if val:
                norm_link = self._normalize_link(str(val))
                if norm_link != val:
                    links_changed = True
                setattr(new_links, field_name, norm_link)
                
        seen_links: set[str] = set()
        for i, link in enumerate(p.links.other):
            norm_link = self._normalize_link(str(link))
            if norm_link:
                if norm_link not in seen_links:
                    seen_links.add(norm_link)
                    new_links.other.append(norm_link)
                if norm_link != str(link) or len(new_links.other) - 1 != i:
                    links_changed = True
            else:
                links_changed = True

        if links_changed:
            p.links = new_links
            self._add_provenance(p, "links", "link_normalization")

        # 7. Skill Normalization & Deduplication
        new_skills = []
        skills_changed = False
        seen_skills: set[str] = set()
        for i, skill in enumerate(p.skills):
            norm_name = self._normalize_skill_name(skill.name)
            canonical = self._skill_key(norm_name)
            
            if canonical not in seen_skills:
                seen_skills.add(canonical)
                if norm_name != skill.name:
                    new_skill = Skill(
                        name=norm_name,
                        confidence=skill.confidence,
                        sources=skill.sources,
                        level=skill.level,
                        years_of_experience=skill.years_of_experience,
                        last_used_year=skill.last_used_year
                    )
                    new_skills.append(new_skill)
                    skills_changed = True
                else:
                    new_skills.append(skill)
            else:
                # Deduplicated
                skills_changed = True
                
        if skills_changed:
            p.skills = new_skills
            self._add_provenance(p, "skills", "skill_normalization")

        # 8. Date Normalization for Experience
        exp_changed = False
        for i, exp in enumerate(p.experience):
            norm_start, s_changed = self._normalize_date_field(exp.start)
            norm_end, e_changed = self._normalize_date_field(exp.end)
            
            new_title = self._normalize_name(exp.title) if exp.title else None
            new_company = self._normalize_name(exp.company) if exp.company else None
            new_summary = self._normalize_name(exp.summary) if exp.summary else None
            
            t_changed = new_title != exp.title
            c_changed = new_company != exp.company
            summ_changed = new_summary != exp.summary
            
            loc_changed = False
            new_loc = exp.location
            if exp.location is not None:
                new_loc, loc_changed = self._normalize_location(exp.location)

            if s_changed or e_changed or t_changed or c_changed or summ_changed or loc_changed:
                exp_changed = True
                # Mutating the deep copy is safe here
                p.experience[i].start = norm_start
                p.experience[i].end = norm_end
                p.experience[i].title = new_title
                p.experience[i].company = new_company
                p.experience[i].summary = new_summary
                p.experience[i].location = new_loc
                
        if exp_changed:
            self._add_provenance(p, "experience", "experience_normalization")

        # 9. Date Normalization for Education
        edu_changed = False
        for i, edu in enumerate(p.education):
            norm_end, e_changed = self._normalize_date_field(edu.end_year)
            if norm_end and isinstance(norm_end, str) and len(norm_end) >= 4:
                norm_end = norm_end[:4]
            
            new_inst = self._normalize_name(edu.institution) if edu.institution else None
            new_field = self._normalize_name(edu.field) if edu.field else None
            
            i_changed = new_inst != edu.institution
            f_changed = new_field != edu.field
            
            if e_changed or i_changed or f_changed:
                edu_changed = True
                p.education[i].end_year = norm_end
                p.education[i].institution = new_inst
                p.education[i].field = new_field

        if edu_changed:
            self._add_provenance(p, "education", "education_normalization")

        return p

    def _add_provenance(self, profile: CandidateProfile, field_path: str, method: str) -> None:
        """Append a provenance record indicating the field was normalised, and update existing flags."""
        profile.provenance.append(
            ProvenanceRecord(
                field=field_path,
                source="normalizer",
                normalised=True,
                method=method,
            )
        )
        for prov in profile.provenance:
            if prov.field == field_path or prov.field.startswith(f"{field_path}[") or prov.field.startswith(f"{field_path}."):
                prov.normalised = True

    def _normalize_name(self, value: str, title_case: bool = False) -> str:
        """Trim whitespace and collapse multiple spaces into one. Optionally apply title case."""
        cleaned = re.sub(r"\s+", " ", value).strip()
        if title_case:
            cleaned = cleaned.title()
        return cleaned

    def _normalize_email(self, email: str) -> Optional[str]:
        """Lowercase, trim, and validate."""
        cleaned = email.strip().lower()
        if re.match(r"^[^@]+@[^@]+\.[^@]+$", cleaned):
            return cleaned
        return None

    def _normalize_phone(self, phone: str) -> Optional[str]:
        """Convert to E.164 using phonenumbers with 'IN' as default region."""
        try:
            parsed = phonenumbers.parse(phone, "IN")
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            pass
        return None

    def _normalize_skill_name(self, name: str) -> str:
        """Canonicalize skill against taxonomy."""
        cleaned = self._normalize_name(name)
        lower_key = cleaned.lower()
        return self.taxonomy.get(lower_key, cleaned)

    @staticmethod
    def _skill_key(skill_name: str) -> str:
        return skill_name.strip().lower()

    def _normalize_link(self, url: str) -> Optional[str]:
        """Trim whitespace, lowercase hostname, remove trailing slash."""
        cleaned = url.strip()
        try:
            parsed = urlparse(cleaned)
            # if no scheme, it might parse weirdly
            if not parsed.scheme:
                parsed = urlparse(f"https://{cleaned}")
                
            netloc = parsed.netloc.lower()
            path = parsed.path.rstrip("/")
            
            unparsed = urlunparse((parsed.scheme, netloc, path, parsed.params, parsed.query, parsed.fragment))
            return unparsed
        except Exception:
            return None

    def _normalize_location(self, loc: Location) -> tuple[Location, bool]:
        """Normalize whitespace in Location fields."""
        c_city = self._normalize_name(loc.city) if loc.city else None
        c_region = self._normalize_name(loc.region) if loc.region else None
        c_country = self._normalize_name(loc.country) if loc.country else None
        c_postal = self._normalize_name(loc.postal_code) if loc.postal_code else None
        c_raw = self._normalize_name(loc.raw) if loc.raw else None
        
        # Extract city from raw if not provided explicitly
        if c_city is None and c_raw:
            cities = re.compile(r"\b(Bangalore|Bengaluru|Mumbai|Delhi|Hyderabad|Pune)\b", re.IGNORECASE)
            match = cities.search(c_raw)
            if match:
                c_city = match.group(1).capitalize()
        
        changed = (
            c_city != loc.city or
            c_region != loc.region or
            c_country != loc.country or
            c_postal != loc.postal_code or
            c_raw != loc.raw
        )
        
        if not changed:
            return loc, False
            
        return Location(
            city=c_city,
            region=c_region,
            country=c_country,
            postal_code=c_postal,
            raw=c_raw
        ), True

    def _normalize_date_field(self, date_val: Any) -> tuple[Any, bool]:
        """
        Parse date_val and return a YYYY-MM formatted string.
        Returns (normalized_value, changed_flag).
        """
        if not date_val:
            return date_val, False
        if isinstance(date_val, str):
            parsed = parse_date_string(date_val)
            if parsed:
                formatted = parsed.strftime("%Y-%m")
                return formatted, formatted != date_val
            return None, True
        from datetime import date
        if isinstance(date_val, date):
            return date_val.strftime("%Y-%m"), True
        return date_val, False
