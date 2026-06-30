"""
adapters package — source-specific data ingestion layer.

This package contains the anti-corruption layer between raw, source-specific
data formats and the canonical :class:`~src.models.CandidateProfile` schema.

Exports
-------
* :class:`~base.SourceAdapter` — abstract base class for all adapters.
* :class:`~base.AdapterError` — exception raised on adapter failure.
* :class:`~ats_adapter.ATSAdapter` — ATS JSON adapter (Phase 1 stub).
* :class:`~resume_adapter.ResumeAdapter` — résumé PDF adapter (Phase 1 stub).
"""

from .ats_adapter import ATSAdapter
from .base import AdapterError, SourceAdapter
from .resume_adapter import ResumeAdapter

__all__ = [
    "SourceAdapter",
    "AdapterError",
    "ATSAdapter",
    "ResumeAdapter",
]
