"""
projector package — configurable output shaping.

Exports
-------
* :class:`~projection_engine.ProjectionEngine` — main projection component.
* :class:`~exceptions.ProjectionError` — exception raised during projection.
"""

from .exceptions import ProjectionError
from .projection_engine import ProjectionEngine

__all__ = ["ProjectionEngine", "ProjectionError"]
