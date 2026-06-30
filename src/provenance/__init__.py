"""
provenance package — audit trail construction and querying.

Exports
-------
* :class:`~provenance_tracker.ProvenanceTracker` — builds and queries provenance records.
"""

from .provenance_tracker import ProvenanceTracker

__all__ = ["ProvenanceTracker"]
