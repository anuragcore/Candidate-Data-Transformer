"""
Exceptions for the projection layer.
"""

from __future__ import annotations


class ProjectionError(Exception):
    """
    Raised when a projection fails.
    
    This occurs if:
    1. A projection path is fundamentally un-parseable (e.g., unmatched brackets).
    2. A required field is missing from the canonical profile, and the
       projection configuration's ``on_missing`` strategy is set to ``RAISE``.
    """
    pass
