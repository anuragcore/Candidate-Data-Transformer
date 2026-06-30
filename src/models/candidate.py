"""
Canonical Pydantic data models for the Candidate Data Transformer.

These models form the single source of truth (the "canonical schema") for
every data structure flowing through the pipeline.  All adapters, normalizers,
and projectors must produce or consume these types — never raw dicts.

Design principles
-----------------
* **Immutability-friendly**: fields are typed and validated by Pydantic v2.
* **Optional everywhere it makes sense**: upstream sources are rarely complete.
* **Rich docstrings**: every field documents its semantic meaning and origin.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SkillLevel(str, Enum):
    """Self-reported or inferred proficiency level for a skill."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    UNKNOWN = "unknown"


class EducationDegree(str, Enum):
    """Standardised degree classifications."""

    HIGH_SCHOOL = "high_school"
    ASSOCIATE = "associate"
    BACHELOR = "bachelor"
    MASTER = "master"
    DOCTORATE = "doctorate"
    CERTIFICATE = "certificate"
    BOOTCAMP = "bootcamp"
    OTHER = "other"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class Location(BaseModel):
    """
    Structured representation of a geographic location.
    """

    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    
    # Internal fields
    postal_code: Optional[str] = None
    raw: Optional[str] = Field(
        default=None,
        description="Original location string before normalisation.",
    )

    model_config = {"frozen": True}


class Links(BaseModel):
    """
    Structured representation of external profile links.
    """
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: list[str] = Field(default_factory=list)


class Skill(BaseModel):
    """
    A single skill possessed by the candidate.
    """

    name: str
    confidence: float = Field(default=1.0)
    sources: list[str] = Field(default_factory=list)
    
    # Internal fields
    level: SkillLevel = SkillLevel.UNKNOWN
    years_of_experience: Optional[float] = None
    last_used_year: Optional[int] = None

    model_config = {"frozen": True}


class Experience(BaseModel):
    """
    A single professional experience entry (a job or role).
    """

    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = Field(default=None, description="Start date in YYYY-MM")
    end: Optional[str] = Field(default=None, description="End date in YYYY-MM")
    summary: Optional[str] = None
    
    # Internal fields
    is_current: bool = False
    skills_used: list[str] = Field(default_factory=list)
    location: Optional[Location] = None
    source: Optional[str] = None


class Education(BaseModel):
    """
    A single education entry (degree, certificate, course, etc.).
    """

    institution: Optional[str] = None
    degree: EducationDegree = EducationDegree.UNKNOWN
    field: Optional[str] = None
    end_year: Optional[str] = None
    
    # Internal fields
    start_date: Optional[date] = None
    gpa: Optional[float] = None
    is_completed: bool = True
    source: Optional[str] = None


class ProvenanceRecord(BaseModel):
    """
    An audit trail entry describing where a piece of data came from.
    """

    field: str
    source: str
    method: Optional[str] = None
    
    # Internal fields
    raw_value: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    normalised: bool = False


# ---------------------------------------------------------------------------
# Root canonical model
# ---------------------------------------------------------------------------


class CandidateProfile(BaseModel):
    """
    The canonical, unified representation of a job candidate.
    """

    candidate_id: UUID = Field(default_factory=uuid4)
    full_name: Optional[str] = None
    emails: list[EmailStr] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    location: Optional[Location] = None
    links: Links = Field(default_factory=Links)
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    overall_confidence: float = Field(default=1.0)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"validate_assignment": True}
