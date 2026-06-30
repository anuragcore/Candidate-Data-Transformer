"""
Phase 2 tests — Source Parsing & Extraction.

Tests cover:
* ATSAdapter: validation, full parse, minimal parse, malformed JSON, unknown keys
* ResumeAdapter: validation, full parse, missing email, missing phone, links
* Text extractors: emails, phones, LinkedIn, GitHub, skill taxonomy matching
* Section parser: experience detection, education detection, empty input
* Date parser: all supported formats, present token, unrecognised input

All tests are deterministic and require no network access.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# ATSAdapter tests
# ---------------------------------------------------------------------------


class TestATSAdapterValidation:
    """validate_source() error handling."""

    def test_missing_file_raises_adapter_error(self, tmp_path: Path) -> None:
        from src.adapters import ATSAdapter
        from src.adapters.base import AdapterError

        adapter = ATSAdapter(path=tmp_path / "ghost.json")
        with pytest.raises(AdapterError, match="not found"):
            adapter.validate_source()

    def test_malformed_json_raises_adapter_error(self, malformed_ats_path: Path) -> None:
        from src.adapters import ATSAdapter
        from src.adapters.base import AdapterError

        adapter = ATSAdapter(path=malformed_ats_path)
        with pytest.raises(AdapterError, match="not valid JSON"):
            adapter.validate_source()

    def test_valid_file_does_not_raise(self, sample_ats_path: Path) -> None:
        from src.adapters import ATSAdapter

        adapter = ATSAdapter(path=sample_ats_path)
        adapter.validate_source()  # Must not raise.


class TestATSAdapterParse:
    """parse() — field extraction and fault tolerance."""

    def test_full_ats_json_populates_all_fields(self, sample_ats_path: Path) -> None:
        """All fields in the sample fixture must map to the profile."""
        from src.adapters import ATSAdapter

        profile = ATSAdapter(path=sample_ats_path).parse()

        assert profile.full_name == "John Doe"
        assert "john.doe@example.com" in profile.emails
        assert any("+91" in p or "9876543210" in p for p in profile.phones)
        assert profile.headline == "Senior Software Engineer"
        assert profile.years_experience == 6.0
        assert profile.location is not None
        assert "Bangalore" in (profile.location.raw or "")

    def test_full_ats_json_extracts_skills(self, sample_ats_path: Path) -> None:
        from src.adapters import ATSAdapter

        profile = ATSAdapter(path=sample_ats_path).parse()
        skill_names = {s.name for s in profile.skills}

        assert "Python" in skill_names
        assert "React" in skill_names
        assert "PostgreSQL" in skill_names
        assert "Docker" in skill_names

    def test_full_ats_json_extracts_experience(self, sample_ats_path: Path) -> None:
        from src.adapters import ATSAdapter

        profile = ATSAdapter(path=sample_ats_path).parse()

        assert len(profile.experience) == 2
        titles = {e.title for e in profile.experience}
        assert "Senior Software Engineer" in titles
        assert "Software Engineer" in titles

    def test_full_ats_json_extracts_education(self, sample_ats_path: Path) -> None:
        from src.adapters import ATSAdapter
        from src.models import EducationDegree

        profile = ATSAdapter(path=sample_ats_path).parse()

        assert len(profile.education) == 1
        edu = profile.education[0]
        assert "Indian Institute of Technology" in (edu.institution or "")
        assert edu.degree == EducationDegree.BACHELOR
        assert edu.gpa == pytest.approx(8.7)

    def test_full_ats_json_extracts_links(self, sample_ats_path: Path) -> None:
        from src.adapters import ATSAdapter

        profile = ATSAdapter(path=sample_ats_path).parse()
        link_strs = [str(lk) for lk in profile.links]

        assert any("linkedin.com" in lk for lk in link_strs)
        assert any("github.com" in lk for lk in link_strs)

    def test_full_ats_provenance_populated(self, sample_ats_path: Path) -> None:
        from src.adapters import ATSAdapter

        profile = ATSAdapter(path=sample_ats_path).parse()

        # Provenance must exist and reference the ATS source.
        assert len(profile.provenance) > 0
        assert all(
            sample_ats_path.name in r.source for r in profile.provenance
        )

    def test_minimal_json_leaves_optional_fields_empty(self, minimal_ats_path: Path) -> None:
        """Only candidateName is provided — all other fields must be None or []."""
        from src.adapters import ATSAdapter

        profile = ATSAdapter(path=minimal_ats_path).parse()

        assert profile.full_name == "Jane Smith"
        assert profile.emails == []
        assert profile.phones == []
        assert profile.skills == []
        assert profile.experience == []
        assert profile.education == []
        assert profile.years_experience is None
        assert profile.location is None

    def test_malformed_json_raises_adapter_error(self, malformed_ats_path: Path) -> None:
        from src.adapters import ATSAdapter
        from src.adapters.base import AdapterError

        with pytest.raises(AdapterError):
            ATSAdapter(path=malformed_ats_path).parse()

    def test_unknown_keys_are_silently_ignored(self, tmp_path: Path) -> None:
        """Extra keys in ATS JSON must not cause failures."""
        from src.adapters import ATSAdapter

        data = {
            "candidateName": "Test User",
            "unknownField": "some_value",
            "anotherWeirdKey": [1, 2, 3],
        }
        path = tmp_path / "extra_keys.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        profile = ATSAdapter(path=path).parse()
        assert profile.full_name == "Test User"

    def test_invalid_email_is_skipped(self, tmp_path: Path) -> None:
        """A malformed email in ATS JSON must be silently dropped."""
        from src.adapters import ATSAdapter

        data = {"candidateName": "Bad Email", "primaryEmail": "not-an-email"}
        path = tmp_path / "bad_email.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        profile = ATSAdapter(path=path).parse()
        assert profile.emails == []

    def test_all_skill_source_tags_are_ats(self, sample_ats_path: Path) -> None:
        from src.adapters import ATSAdapter

        profile = ATSAdapter(path=sample_ats_path).parse()
        for skill in profile.skills:
            assert skill.sources == ["ats"]

    def test_experience_current_flag(self, sample_ats_path: Path) -> None:
        """The first experience entry (Present) should be flagged as current."""
        from src.adapters import ATSAdapter

        profile = ATSAdapter(path=sample_ats_path).parse()
        current_roles = [e for e in profile.experience if e.is_current]
        assert len(current_roles) >= 1


# ---------------------------------------------------------------------------
# ResumeAdapter tests
# ---------------------------------------------------------------------------


class TestResumeAdapterValidation:
    """validate_source() error handling for PDFs."""

    def test_missing_file_raises_adapter_error(self, tmp_path: Path) -> None:
        from src.adapters import ResumeAdapter
        from src.adapters.base import AdapterError

        adapter = ResumeAdapter(path=tmp_path / "ghost.pdf")
        with pytest.raises(AdapterError, match="not found"):
            adapter.validate_source()

    def test_wrong_extension_raises_adapter_error(self, tmp_path: Path) -> None:
        from src.adapters import ResumeAdapter
        from src.adapters.base import AdapterError

        txt_file = tmp_path / "resume.txt"
        txt_file.write_text("not a pdf")
        adapter = ResumeAdapter(path=txt_file)
        with pytest.raises(AdapterError, match=".pdf"):
            adapter.validate_source()

    def test_valid_pdf_does_not_raise(self, sample_resume_pdf: Path) -> None:
        from src.adapters import ResumeAdapter

        adapter = ResumeAdapter(path=sample_resume_pdf)
        adapter.validate_source()  # Must not raise.


class TestResumeAdapterParse:
    """parse() — extraction from realistic PDF résumé."""

    def test_full_resume_extracts_email(self, sample_resume_pdf: Path) -> None:
        from src.adapters import ResumeAdapter

        profile = ResumeAdapter(path=sample_resume_pdf).parse()
        assert "alice.wonderland@example.com" in profile.emails

    def test_full_resume_extracts_phone(self, sample_resume_pdf: Path) -> None:
        from src.adapters import ResumeAdapter

        profile = ResumeAdapter(path=sample_resume_pdf).parse()
        # Phone digits must appear in at least one extracted phone string.
        all_phones = " ".join(profile.phones)
        assert "415" in all_phones or "5550199" in all_phones

    def test_full_resume_extracts_linkedin(self, sample_resume_pdf: Path) -> None:
        from src.adapters import ResumeAdapter

        profile = ResumeAdapter(path=sample_resume_pdf).parse()
        link_strs = [str(lk) for lk in profile.links]
        assert any("linkedin.com" in lk for lk in link_strs)

    def test_full_resume_extracts_github(self, sample_resume_pdf: Path) -> None:
        from src.adapters import ResumeAdapter

        profile = ResumeAdapter(path=sample_resume_pdf).parse()
        link_strs = [str(lk) for lk in profile.links]
        assert any("github.com" in lk for lk in link_strs)

    def test_full_resume_extracts_skills(self, sample_resume_pdf: Path) -> None:
        from src.adapters import ResumeAdapter

        profile = ResumeAdapter(path=sample_resume_pdf).parse()
        skill_names = {s.name for s in profile.skills}

        assert "Python" in skill_names
        assert "React" in skill_names
        assert "Docker" in skill_names

    def test_full_resume_extracts_experience(self, sample_resume_pdf: Path) -> None:
        from src.adapters import ResumeAdapter

        profile = ResumeAdapter(path=sample_resume_pdf).parse()
        assert len(profile.experience) >= 1

    def test_full_resume_extracts_education(self, sample_resume_pdf: Path) -> None:
        from src.adapters import ResumeAdapter

        profile = ResumeAdapter(path=sample_resume_pdf).parse()
        assert len(profile.education) >= 1

    def test_resume_no_email_returns_empty_emails(self, resume_no_email_pdf: Path) -> None:
        from src.adapters import ResumeAdapter

        profile = ResumeAdapter(path=resume_no_email_pdf).parse()
        assert profile.emails == []

    def test_resume_no_phone_returns_empty_phones(self, resume_no_phone_pdf: Path) -> None:
        from src.adapters import ResumeAdapter

        profile = ResumeAdapter(path=resume_no_phone_pdf).parse()
        assert profile.phones == []

    def test_all_skill_source_tags_are_resume(self, sample_resume_pdf: Path) -> None:
        from src.adapters import ResumeAdapter

        profile = ResumeAdapter(path=sample_resume_pdf).parse()
        for skill in profile.skills:
            assert skill.sources == ["resume"]

    def test_provenance_records_present(self, sample_resume_pdf: Path) -> None:
        from src.adapters import ResumeAdapter

        profile = ResumeAdapter(path=sample_resume_pdf).parse()
        assert len(profile.provenance) > 0

    def test_provenance_method_annotation(self, sample_resume_pdf: Path) -> None:
        """Provenance notes must include the extraction method."""
        from src.adapters import ResumeAdapter
    
        profile = ResumeAdapter(path=sample_resume_pdf).parse()
        notes = [r.method for r in profile.provenance if r.method]
        assert len(notes) > 0

    def test_custom_taxonomy_is_used(self, tmp_pdf_factory: Any) -> None:
        """ResumeAdapter should use a caller-supplied taxonomy."""
        from src.adapters import ResumeAdapter

        custom_taxonomy = {"superskill": "SuperSkill™"}
        pdf_path = tmp_pdf_factory("Alex Dev\nalex@test.com\n\nSKILLS\nsuperskill")
        profile = ResumeAdapter(path=pdf_path, skill_taxonomy=custom_taxonomy).parse()
        skill_names = {s.name for s in profile.skills}
        assert "SuperSkill™" in skill_names


# ---------------------------------------------------------------------------
# Text extractor unit tests
# ---------------------------------------------------------------------------


class TestExtractEmails:
    def test_single_email(self) -> None:
        from src.utils import extract_emails
        assert extract_emails("Contact: user@example.com") == ["user@example.com"]

    def test_multiple_emails(self) -> None:
        from src.utils import extract_emails
        result = extract_emails("a@b.com and c@d.org")
        assert "a@b.com" in result
        assert "c@d.org" in result

    def test_no_email_returns_empty(self) -> None:
        from src.utils import extract_emails
        assert extract_emails("No email here") == []

    def test_deduplication(self) -> None:
        from src.utils import extract_emails
        result = extract_emails("foo@bar.com foo@bar.com FOO@BAR.COM")
        assert len(result) == 1
        assert result[0] == "foo@bar.com"

    def test_empty_string(self) -> None:
        from src.utils import extract_emails
        assert extract_emails("") == []


class TestExtractPhones:
    def test_international_phone(self) -> None:
        from src.utils import extract_phones
        result = extract_phones("Call +91 9876543210")
        assert len(result) >= 1
        assert any("9876543210" in p for p in result)

    def test_us_phone(self) -> None:
        from src.utils import extract_phones
        result = extract_phones("(415) 555-0100")
        assert len(result) >= 1

    def test_no_phone_returns_empty(self) -> None:
        from src.utils import extract_phones
        assert extract_phones("No phone here") == []

    def test_short_number_not_extracted(self) -> None:
        from src.utils import extract_phones
        # Reference: 12345 — too short to be a real phone.
        result = extract_phones("Ref: 12345")
        assert result == []


class TestExtractLinks:
    def test_linkedin_extracted(self) -> None:
        from src.utils import extract_links
        result = extract_links("See https://linkedin.com/in/johndoe for profile")
        assert "https://linkedin.com/in/johndoe" in result["linkedin"]
        assert result["github"] == []

    def test_github_extracted(self) -> None:
        from src.utils import extract_links
        result = extract_links("Code at https://github.com/johndoe")
        assert "https://github.com/johndoe" in result["github"]
        assert result["linkedin"] == []

    def test_both_extracted(self) -> None:
        from src.utils import extract_links
        text = "https://linkedin.com/in/alice and https://github.com/alice"
        result = extract_links(text)
        assert len(result["linkedin"]) == 1
        assert len(result["github"]) == 1

    def test_no_links_returns_empty_lists(self) -> None:
        from src.utils import extract_links
        result = extract_links("Plain text, no links.")
        assert result["linkedin"] == []
        assert result["github"] == []

    def test_empty_string(self) -> None:
        from src.utils import extract_links
        result = extract_links("")
        assert result == {"linkedin": [], "github": []}


class TestExtractSkills:
    TAXONOMY = {
        "python": "Python",
        "react": "React",
        "javascript": "JavaScript",
        "machine learning": "Machine Learning",
        "go": "Go",
    }

    def test_exact_match(self) -> None:
        from src.utils import extract_skills
        result = extract_skills("I know Python.", self.TAXONOMY)
        assert "Python" in result

    def test_case_insensitive(self) -> None:
        from src.utils import extract_skills
        result = extract_skills("Expertise: PYTHON, React", self.TAXONOMY)
        assert "Python" in result
        assert "React" in result

    def test_multi_word_skill(self) -> None:
        from src.utils import extract_skills
        result = extract_skills("Experienced in machine learning", self.TAXONOMY)
        assert "Machine Learning" in result

    def test_skill_not_in_taxonomy_not_returned(self) -> None:
        from src.utils import extract_skills
        result = extract_skills("Knows Rust and Haskell", self.TAXONOMY)
        assert result == []

    def test_empty_text_returns_empty(self) -> None:
        from src.utils import extract_skills
        assert extract_skills("", self.TAXONOMY) == []

    def test_empty_taxonomy_returns_empty(self) -> None:
        from src.utils import extract_skills
        assert extract_skills("Python React", {}) == []

    def test_no_false_positive_partial_word(self) -> None:
        from src.utils import extract_skills
        # "go" should not match inside "django" or "google"
        result = extract_skills("Uses Django and Google Cloud", {"go": "Go"})
        assert "Go" not in result


# ---------------------------------------------------------------------------
# Section parser unit tests
# ---------------------------------------------------------------------------


class TestDetectSections:
    def test_experience_section_detected(self) -> None:
        from src.utils import detect_sections

        lines = [
            "John Doe",
            "EXPERIENCE",
            "Engineer at Acme",
            "Jan 2020 - Present",
        ]
        sections = detect_sections(lines)
        assert "experience" in sections
        assert any("Acme" in ln for ln in sections["experience"])

    def test_education_section_detected(self) -> None:
        from src.utils import detect_sections

        lines = ["EDUCATION", "Bachelor of Science", "MIT", "2015 - 2019"]
        sections = detect_sections(lines)
        assert "education" in sections
        assert any("MIT" in ln for ln in sections["education"])

    def test_empty_lines_returns_header_only(self) -> None:
        from src.utils import detect_sections

        sections = detect_sections([])
        assert "header" in sections
        assert sections["header"] == []

    def test_unrecognised_header_stays_in_previous_section(self) -> None:
        from src.utils import detect_sections

        lines = ["EXPERIENCE", "Some Company", "RANDOM UNRECOGNISED HEADER", "Some text"]
        sections = detect_sections(lines)
        # "RANDOM UNRECOGNISED HEADER" doesn't trigger a new section.
        assert "experience" in sections


class TestDateParser:
    def test_month_year_format(self) -> None:
        from src.utils import parse_date_string
        from datetime import date
    
        assert parse_date_string("Jan 2020") == date(2020, 1, 1)

    def test_full_month_name(self) -> None:
        from src.utils import parse_date_string
        from datetime import date

        assert parse_date_string("March 2019") == date(2019, 3, 1)

    def test_iso_month(self) -> None:
        from src.utils import parse_date_string
        from datetime import date

        assert parse_date_string("2020-06") == date(2020, 6, 1)

    def test_year_only(self) -> None:
        from src.utils import parse_date_string
        from datetime import date

        assert parse_date_string("2018") == date(2018, 1, 1)

    def test_present_returns_none(self) -> None:
        from src.utils import parse_date_string

        assert parse_date_string("Present") is None
        assert parse_date_string("Current") is None

    def test_unrecognised_returns_none(self) -> None:
        from src.utils import parse_date_string

        assert parse_date_string("not a date") is None
        assert parse_date_string("") is None
