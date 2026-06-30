"""
Confidence Engine output models.
"""

from typing import Any
from pydantic import BaseModel, Field


class FieldConfidence(BaseModel):
    """
    Represents the confidence score assigned to a specific field.

    Attributes
    ----------
    field_name:
        The name of the field (e.g. "emails", "full_name").
    value:
        The resolved value of the field.
    confidence:
        The deterministic confidence score [0.0 - 1.0].
    sources:
        The sources that corroborated this value (e.g. ["ats", "resume"]).
    reason:
        The reason code for the assigned confidence.
    """

    field_name: str
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)
    reason: str
