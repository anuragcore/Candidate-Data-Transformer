"""
validator package — semantic business-rule validation.

Exports
-------
* :class:`~validation_engine.ValidationEngine` — validates a merged profile.
* :class:`~validation_engine.ValidationResult` — result dataclass.
"""

from .validation_engine import ValidationEngine, ValidationResult

__all__ = ["ValidationEngine", "ValidationResult"]
