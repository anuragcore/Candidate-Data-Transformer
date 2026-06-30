"""
merger/models.py — data models for the MergeEngine output.

These models exist solely to make merge decisions **explainable** and
**traceable**.  Every non-trivial decision the engine makes is recorded
as a :class:`MergeDecision`, and the final output is wrapped in a
:class:`MergeResult` that carries both the merged profile and the full
decision log.

Design notes
------------
* Models are intentionally **separate** from ``src/models/`` because they
  describe the *merging process* rather than the *candidate data* itself.
* All fields are optional where the decision context may be incomplete
  (e.g. when one profile had no value at all).
* ``MergeDecision`` is frozen so the audit log is immutable once written.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.models import CandidateProfile


# ---------------------------------------------------------------------------
# Merge reason vocabulary
# ---------------------------------------------------------------------------

class MergeReason(str, Enum):
    """
    Controlled vocabulary for why a particular value was chosen.

    Using an enum (rather than free-text strings) makes downstream
    reporting, filtering, and testing deterministic.
    """

    RESUME_PRIORITY = "resume_priority"
    """Resume source takes precedence for this field by policy."""

    ATS_PRIORITY = "ats_priority"
    """ATS source takes precedence for this field by policy."""

    ONLY_VALUE = "only_value"
    """Only one profile had a non-null value — no conflict."""

    UNION = "union"
    """Both values were kept (list union / complement merge)."""

    DEDUPLICATION = "deduplication"
    """Identical values from both sources — kept once."""

    LARGER_VALUE = "larger_value"
    """The numerically larger value was preferred (e.g. years_experience)."""

    FIELD_LEVEL_MERGE = "field_level_merge"
    """Sub-fields merged independently (e.g. Location fields)."""

    NO_DATA = "no_data"
    """Both profiles had no data for this field — result is null/empty."""


# ---------------------------------------------------------------------------
# Per-decision record
# ---------------------------------------------------------------------------

class MergeDecision(BaseModel):
    """
    An immutable record of a single field-level merge decision.

    Every time the :class:`MergeEngine` makes a non-trivial choice
    (conflict resolution, deduplication, union, etc.) it appends one
    ``MergeDecision`` to the decision log.

    Attributes
    ----------
    field_name:
        Dot-separated path of the canonical field that was resolved
        (e.g. ``"full_name"``, ``"location.city"``, ``"skills[2].name"``).
    chosen_value:
        The value that was selected for the merged profile.  Stored as
        ``Any`` because fields range from scalars to complex objects.
    discarded_value:
        The value that was *not* selected, if a conflict existed.
        ``None`` when only one source had data (no conflict).
    reason:
        The :class:`MergeReason` enum member explaining the decision.
    source_a_label:
        Human-readable label for the first input profile's source
        (e.g. ``"ats"``).  Populated from ``ProvenanceRecord`` when
        available, otherwise ``"profile_a"``.
    source_b_label:
        Human-readable label for the second input profile's source.
    notes:
        Optional free-text annotation for edge cases or debugging.
    """

    field_name: str
    chosen_value: Optional[Any] = None
    discarded_value: Optional[Any] = None
    reason: MergeReason
    source_a_label: str = "profile_a"
    source_b_label: str = "profile_b"
    notes: Optional[str] = None

    model_config = {"frozen": True}

    def __str__(self) -> str:  # pragma: no cover
        return (
            f"MergeDecision(field={self.field_name!r}, "
            f"reason={self.reason.value!r}, "
            f"chosen={self.chosen_value!r})"
        )


# ---------------------------------------------------------------------------
# Merge result container
# ---------------------------------------------------------------------------

class MergeResult(BaseModel):
    """
    The complete output of a :meth:`MergeEngine.merge` call.

    Attributes
    ----------
    merged_profile:
        The single, authoritative :class:`~src.models.CandidateProfile`
        produced by combining the two input profiles.
    merge_decisions:
        Ordered list of every :class:`MergeDecision` made during the merge.
        This is the primary explainability / audit artefact.
    profile_a_source:
        Human-readable label for the first input profile (default ``"ats"``).
    profile_b_source:
        Human-readable label for the second input profile (default ``"resume"``).

    Usage
    -----
    ::

        result = engine.merge(ats_profile, resume_profile)
        print(result.merged_profile.full_name)
        for decision in result.merge_decisions:
            print(decision)
    """

    merged_profile: CandidateProfile
    merge_decisions: list[MergeDecision] = Field(default_factory=list)
    profile_a_source: str = "ats"
    profile_b_source: str = "resume"

    @property
    def conflict_count(self) -> int:
        """Number of decisions where a value was discarded (true conflicts)."""
        return sum(
            1 for d in self.merge_decisions if d.discarded_value is not None
        )

    @property
    def field_decisions(self) -> dict[str, MergeDecision]:
        """Index of decisions by field name for O(1) lookup."""
        return {d.field_name: d for d in self.merge_decisions}
