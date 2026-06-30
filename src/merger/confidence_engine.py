"""
Confidence Engine — Phase D.

Assigns deterministic confidence scores to the fields in a merged CandidateProfile
based on the sources of the data and source agreement.

Confidence Strategy:
- ATS only -> 0.90 (single_source_ats)
- Resume only -> 0.80 (single_source_resume)
- Agreement -> 1.00 (source_agreement)
- Conflict -> 0.70 (source_conflict)
- Unknown -> 0.50 (unknown_source)

Confidence represents Source reliability + Source corroboration, not statistical certainty.
"""

from src.models.candidate import CandidateProfile
from src.merger.models import MergeResult


class ConfidenceEngine:
    def __init__(self) -> None:
        # We only score these specific fields
        self.scored_fields = {"full_name", "emails", "phones", "headline", "skills", "location"}

    def _get_base_field(self, field_path: str) -> str:
        """Extract base field name, e.g. 'emails[0]' -> 'emails', 'location.city' -> 'location'"""
        return field_path.split('[')[0].split('.')[0]

    def calculate_confidence(self, result: MergeResult) -> CandidateProfile:
        profile = result.merged_profile

        # Group provenance raw values by base field and source
        field_values_by_source: dict[str, dict[str, set[str]]] = {}
        for f in self.scored_fields:
            field_values_by_source[f] = {"ats": set(), "resume": set()}

        for prov in profile.provenance:
            base = self._get_base_field(prov.field)
            if base in self.scored_fields:
                source_lower = prov.source.lower()
                if "ats" in source_lower or ".json" in source_lower:
                    source_type = "ats"
                elif "resume" in source_lower or ".pdf" in source_lower:
                    source_type = "resume"
                else:
                    source_type = "unknown"
                    
                if source_type in ("ats", "resume"):
                    val = str(prov.raw_value).strip().lower() if prov.raw_value else ""
                    field_values_by_source[base][source_type].add(val)

        # Now compute confidence for each provenance record
        final_field_scores: dict[str, float] = {}

        for prov in profile.provenance:
            base = self._get_base_field(prov.field)
            if base not in self.scored_fields:
                continue
                
            source_lower = prov.source.lower()
            if "ats" in source_lower or ".json" in source_lower:
                source_type = "ats"
            elif "resume" in source_lower or ".pdf" in source_lower:
                source_type = "resume"
            else:
                source_type = "unknown"
            
            if source_type == "unknown":
                prov.confidence = 0.50
            else:
                ats_vals = field_values_by_source[base]["ats"]
                res_vals = field_values_by_source[base]["resume"]
                
                val = str(prov.raw_value).strip().lower() if prov.raw_value else ""
                
                if ats_vals and res_vals:
                    # Both sources provided some data for this field.
                    # Check if they agreed on this specific value.
                    if val in ats_vals and val in res_vals:
                        prov.confidence = 1.00  # Agreement
                    else:
                        prov.confidence = 0.70  # Conflict
                elif ats_vals:
                    prov.confidence = 0.90  # ATS only
                elif res_vals:
                    prov.confidence = 0.80  # Resume only
                else:
                    prov.confidence = 0.50  # Unknown
                    
            final_field_scores[base] = prov.confidence

        # Calculate overall confidence
        if final_field_scores:
            profile.overall_confidence = sum(final_field_scores.values()) / len(final_field_scores)
        else:
            profile.overall_confidence = 1.0

        return profile
