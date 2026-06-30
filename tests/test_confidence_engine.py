"""
Tests for Phase D: Confidence Engine.
"""

from typing import Any

from src.models import (
    CandidateProfile,
    ProvenanceRecord,
    Skill,
    Location,
)
from src.confidence import ConfidenceEngine


def test_confidence_engine():
    # Construct a profile that has overlapping and distinct values
    profile = CandidateProfile.model_construct(
        full_name="John Doe",
        headline="Software Engineer",
        location=Location(city="Bangalore"),
        emails=["john@gmail.com", "doe@yahoo.com", "unknown@gmail.com"],
        phones=["+919876543210"],
        skills=[
            Skill(name="Python"),
            Skill(name="React"),
            Skill(name="Ruby")
        ],
        provenance=[
            # ATS only
            ProvenanceRecord(field="full_name", source="ats.json", raw_value="John Doe"),
            ProvenanceRecord(field="emails[0]", source="ats.json", raw_value="john@gmail.com"),
            ProvenanceRecord(field="skills[0].name", source="ats.json", raw_value="Python"),
            
            # Resume only
            ProvenanceRecord(field="headline", source="resume.pdf", raw_value="Software Engineer"),
            ProvenanceRecord(field="emails[1]", source="resume.pdf", raw_value="doe@yahoo.com"),
            ProvenanceRecord(field="skills[1].name", source="resume.pdf", raw_value="React"),
            
            # Agreement (both ATS and Resume)
            ProvenanceRecord(field="phones[0]", source="ats.json", raw_value="+91 9876543210"),
            ProvenanceRecord(field="phones[0]", source="resume.pdf", raw_value="9876543210"),
            ProvenanceRecord(field="location.city", source="ats.json", raw_value="Bangalore"),
            ProvenanceRecord(field="location", source="resume.pdf", raw_value="Bangalore, India"),
            
            # Missing provenance for unknown@gmail.com and Ruby
        ]
    )

    engine = ConfidenceEngine()
    results = engine.compute(profile)
    
    # We should have scores for: full_name, headline, location, 3 emails, 1 phone, 3 skills = 10 items
    assert len(results) == 10
    
    # Let's map them for easy lookup
    score_map: dict[str, Any] = {}
    for r in results:
        # field_name and value uniquely identify it here
        val_str = str(r.value) if not isinstance(r.value, Skill) else r.value.name
        key = f"{r.field_name}:{val_str}"
        score_map[key] = r

    # ATS Only
    assert score_map["full_name:John Doe"].confidence == 0.90
    assert score_map["full_name:John Doe"].reason == "single_source_ats"
    assert "ats" in score_map["full_name:John Doe"].sources
    assert "resume" not in score_map["full_name:John Doe"].sources

    # Conflict (emails provided by both but different values)
    assert score_map["emails:john@gmail.com"].confidence == 0.70
    assert score_map["emails:john@gmail.com"].reason == "source_conflict"
    assert "ats" in score_map["emails:john@gmail.com"].sources
    
    assert score_map["emails:doe@yahoo.com"].confidence == 0.70
    assert score_map["emails:doe@yahoo.com"].reason == "source_conflict"
    assert "resume" in score_map["emails:doe@yahoo.com"].sources

    # Resume Only
    assert score_map["headline:Software Engineer"].confidence == 0.80
    
    # Agreement
    assert score_map["phones:+919876543210"].confidence == 1.00
    assert "ats" in score_map["phones:+919876543210"].sources
    assert "resume" in score_map["phones:+919876543210"].sources

    assert score_map["location:city='Bangalore' region=None country=None postal_code=None raw=None"].confidence == 1.0

    # Missing provenance (Unknown)
    assert score_map["emails:unknown@gmail.com"].confidence == 0.50
    assert score_map["emails:unknown@gmail.com"].reason == "unknown_source"
    assert len(score_map["emails:unknown@gmail.com"].sources) == 0

    assert score_map["skills:Ruby"].confidence == 0.5
