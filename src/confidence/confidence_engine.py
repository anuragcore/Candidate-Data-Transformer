"""
ConfidenceEngine — assigns deterministic confidence scores to profile fields.
"""

import re
from typing import Any

from src.models import CandidateProfile, Skill, Location
from src.confidence.models import FieldConfidence


class ConfidenceEngine:
    """
    Computes deterministic confidence scores based on source agreement.
    Does not mutate the CandidateProfile.
    """

    def compute(self, profile: CandidateProfile) -> list[FieldConfidence]:
        """
        Compute confidence for eligible fields in the profile.
        """
        results: list[FieldConfidence] = []

        # Scalar fields
        if profile.full_name is not None:
            results.append(self._score_scalar(profile, "full_name", profile.full_name))
        
        if profile.headline is not None:
            results.append(self._score_scalar(profile, "headline", profile.headline))
            
        if profile.location is not None:
            results.append(self._score_scalar(profile, "location", profile.location))

        # List fields
        if profile.emails:
            results.extend(self._score_list(profile, "emails", profile.emails))
            
        if profile.phones:
            results.extend(self._score_list(profile, "phones", profile.phones))
            
        if profile.skills:
            results.extend(self._score_list(profile, "skills", profile.skills))

        return results

    def _score_scalar(self, profile: CandidateProfile, field_name: str, value: Any) -> FieldConfidence:
        """Helper to score a single scalar field."""
        sources = self._extract_sources(profile, field_name, value)
        all_field_sources = self._get_all_sources_for_field(profile, field_name)
        confidence, reason = self._determine_score(sources, all_field_sources)
        
        return FieldConfidence(
            field_name=field_name,
            value=value,
            confidence=confidence,
            sources=sources,
            reason=reason,
        )

    def _score_list(self, profile: CandidateProfile, field_name: str, values: list[Any]) -> list[FieldConfidence]:
        """Helper to score a list of fields."""
        results = []
        for val in values:
            sources = self._extract_sources(profile, field_name, val)
            all_field_sources = self._get_all_sources_for_field(profile, field_name)
            
            confidence, reason = self._determine_score(sources, all_field_sources)
            
            results.append(FieldConfidence(
                field_name=field_name,
                value=val,
                confidence=confidence,
                sources=sources,
                reason=reason,
            ))
        return results

    def _get_all_sources_for_field(self, profile: CandidateProfile, field_prefix: str) -> set[str]:
        sources = set()
        for record in profile.provenance:
            if record.field.split('[')[0].split('.')[0] == field_prefix:
                src_lower = record.source.lower()
                if "ats" in src_lower or ".json" in src_lower:
                    sources.add("ats")
                elif "resume" in src_lower or ".pdf" in src_lower:
                    sources.add("resume")
        return sources

    def _determine_score(self, value_sources: list[str], all_field_sources: set[str]) -> tuple[float, str]:
        """Maps extracted sources to confidence score and reason."""
        if not value_sources:
            return 0.50, "unknown_source"
            
        if "ats" in value_sources and "resume" in value_sources:
            return 1.0, "source_agreement"
            
        # It's a conflict if the field was present in BOTH sources, but THIS value only came from one!
        if "ats" in all_field_sources and "resume" in all_field_sources:
            return 0.70, "source_conflict"
            
        if "ats" in value_sources:
            return 0.90, "single_source_ats"
        elif "resume" in value_sources:
            return 0.80, "single_source_resume"
        else:
            return 0.50, "unknown_source"

    def _clean_string(self, val: Any) -> str:
        """Strips formatting for robust deterministic matching."""
        if isinstance(val, Skill):
            s = val.name
        elif isinstance(val, Location):
            s = val.raw or val.city or ""
        else:
            s = str(val)
            
        # Strip all non-alphanumeric chars and lowercase
        return re.sub(r'[\W_]+', '', s).lower()

    def _extract_sources(self, profile: CandidateProfile, field_prefix: str, value: Any) -> list[str]:
        """
        Scans provenance records for matching values and returns the source names.
        """
        cleaned_val = self._clean_string(value)
        if not cleaned_val:
            return []
            
        sources = set()
        for record in profile.provenance:
            if not getattr(record, "field", "").startswith(field_prefix):
                continue
            if not record.raw_value:
                continue
                
            cleaned_rec = self._clean_string(record.raw_value)
            if not cleaned_rec:
                continue
                
            # Exact match or substring match (if length > 3 to avoid false positives)
            if (cleaned_val == cleaned_rec) or (
                len(cleaned_val) > 3 and (cleaned_val in cleaned_rec or cleaned_rec in cleaned_val)
            ):
                src_lower = record.source.lower()
                if "ats" in src_lower or ".json" in src_lower:
                    sources.add("ats")
                elif "resume" in src_lower or ".pdf" in src_lower:
                    sources.add("resume")
                    
        return sorted(list(sources))
