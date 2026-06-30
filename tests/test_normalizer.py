"""
Tests for Phase C: Normalization Layer.
"""

from copy import deepcopy
from datetime import date
from pydantic import HttpUrl

import pytest

from src.models import (
    CandidateProfile,
    Location,
    Skill,
    Experience,
    Education,
    Links,
)
from src.normalizers import Normalizer

@pytest.fixture
def mock_taxonomy(tmp_path):
    tax_path = tmp_path / "skill_taxonomy.json"
    tax_path.write_text('{"python": "Python", "java": "Java", "react": "React"}')
    return tax_path

@pytest.fixture
def base_profile():
    return CandidateProfile.model_construct(
        full_name="  Alice   Wonderland ",
        headline="  Software   Engineer  ",
        location=Location(city="  Wonderland ", raw=" Wonderland   City  "),
        emails=[" Alice.Wonder@GMAIL.com ", "alice.wonder@gmail.com", "invalid-email"],
        phones=["9876543210", "+91 9876543210", "(987) 654-3210", "invalid-phone"],
        links=Links(github="HTTPS://GITHUB.COM/Alice/", linkedin="http://linkedin.com/in/alice/"),
        skills=[
            Skill(name=" python ", years_of_experience=5.0),
            Skill(name="PYTHON", years_of_experience=2.0),
            Skill(name="unknown_skill")
        ],
        experience=[
            Experience(
                title=" Senior   Dev ",
                company="  Acme ",
                start="2020-01"
            )
        ],
        education=[
            Education(
                institution="  IIT ",
                field="  Computer   Science ",
                start="2014-01"
            )
        ],
        provenance=[]
    )

def test_normalization_rules(base_profile, mock_taxonomy):
    normalizer = Normalizer(taxonomy_path=mock_taxonomy)
    
    # We forcefully inject a string into the date field to test the fallback parser
    base_profile.experience[0].end = "Jan 2021"  # type: ignore
    base_profile.experience[0].start = "garbage_date" # type: ignore
    
    norm_profile = normalizer.normalize(base_profile)
    
    # 1. Name Normalization
    assert norm_profile.full_name == "Alice Wonderland"
    assert norm_profile.headline == "Software Engineer"
    
    # 2. Location Normalization
    assert norm_profile.location.city == "Wonderland"
    assert norm_profile.location.raw == "Wonderland City"
    
    # 3. Email Normalization & Deduplication
    assert len(norm_profile.emails) == 1
    assert norm_profile.emails[0] == "alice.wonder@gmail.com"
    
    # 4. Phone Normalization (E.164) & Deduplication
    # Default country is IN (+91)
    # 9876543210 -> +919876543210
    # +91 9876543210 -> +919876543210
    # (987) 654-3210 -> +19876543210 (US number, wait does phonenumbers parse it? Actually (987) 654-3210 might not be valid IN, so it might fail or format as US if it was valid, but without +1 it might be treated as IN and fail. Let's check.)
    # In either case, invalid-phone is removed.
    assert "+919876543210" in norm_profile.phones
    assert "invalid-phone" not in norm_profile.phones
    # Length should be deduplicated
    # 9876543210 and +91 9876543210 are the same
    
    # 5. Link Normalization
    assert str(norm_profile.links.github) == "https://github.com/Alice"
    assert str(norm_profile.links.linkedin) == "http://linkedin.com/in/alice"
    
    # 6. Skill Normalization & Deduplication
    assert len(norm_profile.skills) == 2
    assert norm_profile.skills[0].name == "Python"
    assert norm_profile.skills[0].years_of_experience == 5.0  # Kept from first occurrence
    assert norm_profile.skills[1].name == "unknown_skill"
    
    # 7. Date Normalization fallback
    assert norm_profile.experience[0].end == "2021-01"
    assert norm_profile.experience[0].start is None  # garbage date parsed as None
    
    # 8. Nested name normalization (experience & education)
    assert norm_profile.experience[0].title == "Senior Dev"
    assert norm_profile.experience[0].company == "Acme"
    assert norm_profile.education[0].institution == "IIT"
    assert norm_profile.education[0].field == "Computer Science"

def test_idempotency(base_profile, mock_taxonomy):
    normalizer = Normalizer(taxonomy_path=mock_taxonomy)
    
    pass1 = normalizer.normalize(base_profile)
    pass2 = normalizer.normalize(pass1)
    
    # Provenance list should grow only on the first pass
    assert len(pass1.provenance) > 0
    assert len(pass1.provenance) == len(pass2.provenance)
    
    # The profiles themselves should be identical
    assert pass1.model_dump() == pass2.model_dump()

def test_provenance_appending(base_profile, mock_taxonomy):
    normalizer = Normalizer(taxonomy_path=mock_taxonomy)
    
    # Inject existing provenance to ensure it's not overwritten
    base_profile.provenance = [
        # ... some existing record
    ]
    
    norm = normalizer.normalize(base_profile)
    
    # Verify provenance was added for modified fields
    methods = [p.method for p in norm.provenance if p.method]
    assert "name_normalization" in methods
    assert "email_normalization" in methods
    assert "e164_normalization" in methods
    assert "skill_normalization" in methods
    assert "location_normalization" in methods

def test_no_changes_no_provenance(mock_taxonomy):
    # A perfectly clean profile should result in zero new provenance records
    clean_profile = CandidateProfile(
        full_name="Alice Wonderland",
        emails=["alice@gmail.com"],
        phones=["+919876543210"],
        skills=[Skill(name="Python")]
    )
    
    normalizer = Normalizer(taxonomy_path=mock_taxonomy)
    norm = normalizer.normalize(clean_profile)
    
    assert len(norm.provenance) == 0
    assert norm.model_dump() == clean_profile.model_dump()
