"""
merger package — deterministic, explainable multi-source profile consolidation.

Exports
-------
* :class:`~merge_engine.MergeEngine` — merges two profiles into one.
* :class:`~confidence_engine.ConfidenceEngine` — evaluates confidence of profile data.
* :class:`~models.MergeResult` — merged profile + full decision log.
* :class:`~models.MergeDecision` — a single field-level merge decision.
* :class:`~models.MergeReason` — controlled reason vocabulary (enum).
"""

from .merge_engine import MergeEngine
from .confidence_engine import ConfidenceEngine
from .models import MergeDecision, MergeReason, MergeResult

__all__ = [
    "MergeEngine",
    "ConfidenceEngine",
    "MergeDecision",
    "MergeReason",
    "MergeResult",
]
