"""
ProvenanceTracker — audit trail builder and query interface (stub).

The ``ProvenanceTracker`` provides a high-level API for creating and querying
:class:`~src.models.ProvenanceRecord` entries on a
:class:`~src.models.CandidateProfile`.

Instead of manually constructing ``ProvenanceRecord`` objects scattered across
adapters and the merge engine, components should use ``ProvenanceTracker`` to
ensure consistent record structure and timestamps.

Current status: **Phase 1 stub** — no tracking logic implemented.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from src.models import CandidateProfile, ProvenanceRecord


class ProvenanceTracker:
    """
    Builds and manages :class:`~src.models.ProvenanceRecord` entries on a
    ``CandidateProfile``.

    Usage (planned)
    ---------------
    ::

        tracker = ProvenanceTracker()
        tracker.record(
            profile=profile,
            field_path="full_name",
            source="ats",
            raw_value="John Doe",
            confidence=0.95,
        )
        records = tracker.get_records(profile, field_path="full_name")
    """

    def record(
        self,
        profile: CandidateProfile,
        field_path: str,
        source: str,
        raw_value: Optional[str] = None,
        confidence: float = 1.0,
        normalised: bool = False,
        notes: Optional[str] = None,
    ) -> ProvenanceRecord:
        """
        Create a :class:`~src.models.ProvenanceRecord` and attach it to
        ``profile.provenance``.

        Parameters
        ----------
        profile:
            The profile to attach the provenance record to.
        field_path:
            Dot-separated path to the field being recorded
            (e.g. ``"emails[0]"``).
        source:
            Logical name of the originating source (``"ats"``, ``"resume"``).
        raw_value:
            The un-normalised value as extracted from the source.
        confidence:
            Confidence score in ``[0.0, 1.0]``.
        normalised:
            Whether the value was modified during normalisation.
        notes:
            Optional notes for debugging.

        Returns
        -------
        ProvenanceRecord
            The newly created record (also appended to ``profile.provenance``).

        TODO (Phase 2):
        ---------------
        * Construct and append a ``ProvenanceRecord`` to ``profile.provenance``.
        * Set ``extracted_at`` to the current UTC time.
        * Return the created record.
        """
        # TODO: Implement provenance record creation and attachment.
        raise NotImplementedError("ProvenanceTracker.record() is not yet implemented.")

    def get_records(
        self,
        profile: CandidateProfile,
        field_path: Optional[str] = None,
        source: Optional[str] = None,
    ) -> list[ProvenanceRecord]:
        """
        Query the provenance records on ``profile``.

        Parameters
        ----------
        profile:
            The profile whose provenance records to query.
        field_path:
            If provided, filter records to those matching this field path.
        source:
            If provided, filter records to those matching this source.

        Returns
        -------
        list[ProvenanceRecord]
            Matching provenance records, ordered by ``extracted_at`` ascending.

        TODO (Phase 2): Implement provenance query with optional filters.
        """
        # TODO: Implement provenance record query.
        raise NotImplementedError(
            "ProvenanceTracker.get_records() is not yet implemented."
        )

    def summarise(self, profile: CandidateProfile) -> dict[str, list[str]]:
        """
        Return a summary mapping each field path to its contributing sources.

        Useful for debugging and audit reporting.

        TODO (Phase 2): Implement provenance summary generation.
        """
        # TODO: Implement provenance summary.
        raise NotImplementedError(
            "ProvenanceTracker.summarise() is not yet implemented."
        )
