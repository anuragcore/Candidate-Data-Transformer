"""
models package — canonical data models for the Candidate Data Transformer.

Exports
-------
* :class:`~candidate.CandidateProfile` — the root canonical schema.
* :class:`~candidate.Skill` — a single normalised skill.
* :class:`~candidate.Experience` — a professional experience entry.
* :class:`~candidate.Education` — an education entry.
* :class:`~candidate.Location` — a structured geographic location.
* :class:`~candidate.ProvenanceRecord` — an audit-trail record.
* :class:`~candidate.SkillLevel` — proficiency level enum.
* :class:`~candidate.EducationDegree` — degree type enum.
* :class:`~config.ProjectionField` — a single field mapping config.
* :class:`~config.ProjectionConfig` — top-level projection config.
* :class:`~config.OnMissingStrategy` — missing-field strategy enum.
"""

from .candidate import (
    CandidateProfile,
    Education,
    EducationDegree,
    Experience,
    Links,
    Location,
    ProvenanceRecord,
    Skill,
    SkillLevel,
)
from .config import OnMissingStrategy, ProjectionConfig, ProjectionField

__all__ = [
    # Canonical profile
    "CandidateProfile",
    "Skill",
    "SkillLevel",
    "Experience",
    "Education",
    "EducationDegree",
    "Location",
    "ProvenanceRecord",
    # Projection config
    "ProjectionField",
    "ProjectionConfig",
    "OnMissingStrategy",
]
