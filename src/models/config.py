"""
Configuration Pydantic models for the projection layer.

The projection layer is responsible for shaping a full ``CandidateProfile``
into a consumer-specific output format.  These configuration models define
*which* fields are included in a projection, where they map from in the
canonical schema, and how missing values should be handled.

Example config (YAML equivalent)
---------------------------------
::

    projection:
      fields:
        - path: "output.name"
          from: "full_name"
          required: true
          on_missing: "raise"

        - path: "output.email"
          from: "emails[0]"
          required: false
          on_missing: "default"
          default_value: ""

        - path: "output.primary_skill"
          from: "skills[0].name"
          required: false
          on_missing: "omit"
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class OnMissingStrategy(str, Enum):
    """
    Strategy to apply when a required source field is absent.

    Attributes
    ----------
    RAISE:
        Raise a ``ValueError`` / pipeline error immediately.
    DEFAULT:
        Substitute a configurable ``default_value``.
    OMIT:
        Silently omit the field from the output document.
    NULL:
        Include the field in the output with a ``null`` / ``None`` value.
    """

    RAISE = "raise"
    DEFAULT = "default"
    OMIT = "omit"
    NULL = "null"


# ---------------------------------------------------------------------------
# Field-level config
# ---------------------------------------------------------------------------


class ProjectionField(BaseModel):
    """
    Configuration for a single field in a projection output.

    Each ``ProjectionField`` describes one mapping from the canonical
    ``CandidateProfile`` schema to a target output document key.

    Attributes
    ----------
    path:
        Dot-separated key path in the **output** document
        (e.g. ``"candidate.contact.email"``).
    from_field:
        Dot-separated path into the **canonical** ``CandidateProfile``
        from which the value is read.  Supports bracket notation for
        list indexing (e.g. ``"emails[0]"`` or ``"skills[0].name"``).
        Aliased from ``"from"`` to avoid collision with Python's keyword.
    required:
        Whether this field must be present in the output.  When ``True``,
        the ``on_missing`` strategy determines error behaviour.
    on_missing:
        How to handle the case where ``from_field`` resolves to ``None``
        or does not exist on the profile.  Defaults to ``OnMissingStrategy.NULL``.
    default_value:
        The fallback value to use when ``on_missing`` is
        ``OnMissingStrategy.DEFAULT``.  May be any JSON-serialisable type.
    transform:
        Optional name of a registered transform function to apply to the
        resolved value before writing it to the output (e.g. ``"uppercase"``
        or ``"strip_whitespace"``).  The actual transform registry lives in
        the projector module.
    description:
        Human-readable description of this field mapping, for documentation
        and debugging purposes.
    """

    path: str = Field(..., description="Output key path (dot-separated).")
    from_field: str = Field(
        ...,
        alias="from",
        description="Source path within CandidateProfile (dot / bracket notation).",
    )
    required: bool = Field(
        default=False,
        description="Whether the field is mandatory in the output.",
    )
    on_missing: OnMissingStrategy = Field(
        default=OnMissingStrategy.NULL,
        description="Behaviour when the source value is absent.",
    )
    default_value: Optional[Any] = Field(
        default=None,
        description="Fallback value used when on_missing=DEFAULT.",
    )
    transform: Optional[str] = Field(
        default=None,
        description="Name of a registered post-resolution transform.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Human-readable description of the mapping.",
    )

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Projection-level config
# ---------------------------------------------------------------------------


class ProjectionConfig(BaseModel):
    """
    Top-level configuration for a named projection.

    A ``ProjectionConfig`` is typically loaded from a YAML or JSON file in the
    ``config/`` directory and passed to the ``ProjectionEngine`` at runtime.

    Attributes
    ----------
    name:
        A short, machine-readable identifier for this projection
        (e.g. ``"ats_export"`` or ``"recruiter_summary"``).
    version:
        Semantic version string for this config, enabling forward compatibility
        checks (e.g. ``"1.0.0"``).
    description:
        Human-readable description of what this projection produces.
    fields:
        Ordered list of field mappings that define the output document shape.
    include_provenance:
        Whether to append provenance metadata to the output document.
    strip_null_fields:
        When ``True``, fields whose resolved value is ``None`` / ``null`` are
        removed from the output entirely (overrides ``on_missing=NULL``).
    """

    name: str = Field(..., description="Machine-readable projection identifier.")
    version: str = Field(
        default="1.0.0",
        description="Semantic version of this projection config.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Human-readable description of the projection.",
    )
    fields: list[ProjectionField] = Field(
        default_factory=list,
        description="Ordered field mappings from canonical schema to output.",
    )
    include_provenance: bool = Field(
        default=False,
        description="Whether to embed provenance metadata in the output.",
    )
    strip_null_fields: bool = Field(
        default=False,
        description="Remove null-valued fields from the output document.",
    )
