"""
tests/test_merge_engine.py — comprehensive tests for the MergeEngine.

Coverage target: 90%+ of src/merger/ code.

Test organisation
-----------------
Each test class isolates one merge rule:

* TestMergeEngineSmokeTest      — basic import, instantiation, result type
* TestMergeName                 — full_name priority + conflict + dedup
* TestMergeHeadline             — headline priority + conflict + dedup
* TestMergeYearsExperience      — max-value rule, one-sided, both-none
* TestMergeEmails               — union, case-insensitive dedup
* TestMergePhones               — union, digit-normalised dedup
* TestMergeLinks                — per-platform priority + unknown union
* TestMergeLocation             — field-by-field merge, conflict, complement
* TestMergeSkills               — union, exact dedup, multi-source flag
* TestMergeExperience           — union, dedup key, résumé-wins on conflict
* TestMergeEducation            — union, dedup key, résumé-wins on conflict
* TestMergeProvenance           — full union, never-discard guarantee
* TestMergeDecisions            — decision log structure and reason values
* TestMergeResult               — MergeResult helpers (conflict_count, etc.)
* TestMergeRobustness           — None fields, empty lists, both-empty profiles
* TestMergeEngineEndToEnd       — realistic ATS + résumé integration test
"""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from src.merger import MergeDecision, MergeEngine, MergeReason, MergeResult
from src.models import (
    CandidateProfile,
    Education,
    EducationDegree,
    Experience,
    Location,
    ProvenanceRecord,
    Skill,
    SkillLevel,
    Links,
)
from pydantic import HttpUrl


# ---------------------------------------------------------------------------
# Shared builder helpers
# ---------------------------------------------------------------------------

def _profile(**kwargs) -> CandidateProfile:
    """Return a minimal CandidateProfile with overrides."""
    return CandidateProfile(**kwargs)


def _skill(name: str, source: str = "ats", level: SkillLevel = SkillLevel.UNKNOWN) -> Skill:
    return Skill(name=name, sources=[source], level=level)


def _exp(
    title: str,
    company: str,
    start: date | None = None,
    end: date | None = None,
    is_current: bool = False,
    source: str = "ats",
) -> Experience:
    return Experience(
        title=title,
        company=company,
        start=start if isinstance(start, str) else start.strftime("%Y-%m") if start else None,
        end=end if isinstance(end, str) else end.strftime("%Y-%m") if end else None,
        is_current=is_current,
        source=source,
    )


def _edu(
    institution: str,
    degree: EducationDegree = EducationDegree.BACHELOR,
    end: date | None = None,
    source: str = "ats",
    gpa: float | None = None,
    field: str | None = None,
) -> Education:
    return Education(
        institution=institution,
        degree=degree,
        end_year=end,
        source=source,
        gpa=gpa,
        field=field,
    )


def _prov(field: str, source: str = "ats") -> ProvenanceRecord:
    return ProvenanceRecord(field=field, source=source)


ENGINE = MergeEngine()


# ===========================================================================
# Smoke tests
# ===========================================================================

class TestMergeEngineSmokeTest:
    def test_importable(self) -> None:
        from src.merger import MergeEngine  # noqa: F401

    def test_instantiation_defaults(self) -> None:
        engine = MergeEngine()
        assert engine is not None

    def test_instantiation_custom_labels(self) -> None:
        engine = MergeEngine(profile_a_label="source1", profile_b_label="source2")
        assert engine is not None

    def test_returns_merge_result(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert isinstance(result, MergeResult)

    def test_result_contains_profile(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert isinstance(result.merged_profile, CandidateProfile)

    def test_result_contains_decisions(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert isinstance(result.merge_decisions, list)

    def test_decisions_are_merge_decision_instances(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        for d in result.merge_decisions:
            assert isinstance(d, MergeDecision)

    def test_does_not_mutate_inputs(self) -> None:
        a = _profile(full_name="Alice")
        b = _profile(full_name="Bob")
        original_a = a.full_name
        original_b = b.full_name
        ENGINE.merge(a, b)
        assert a.full_name == original_a
        assert b.full_name == original_b


# ===========================================================================
# full_name
# ===========================================================================

class TestMergeName:
    def test_resume_wins_on_conflict(self) -> None:
        a = _profile(full_name="John Doe")
        b = _profile(full_name="Johnathan Doe")
        result = ENGINE.merge(a, b)
        assert result.merged_profile.full_name == "Johnathan Doe"

    def test_decision_recorded_on_conflict(self) -> None:
        a = _profile(full_name="John Doe")
        b = _profile(full_name="Johnathan Doe")
        result = ENGINE.merge(a, b)
        d = result.field_decisions.get("full_name")
        assert d is not None
        assert d.reason == MergeReason.RESUME_PRIORITY
        assert d.chosen_value == "Johnathan Doe"
        assert d.discarded_value == "John Doe"

    def test_uses_ats_when_resume_missing(self) -> None:
        a = _profile(full_name="John Doe")
        b = _profile(full_name=None)
        result = ENGINE.merge(a, b)
        assert result.merged_profile.full_name == "John Doe"

    def test_uses_resume_when_ats_missing(self) -> None:
        a = _profile(full_name=None)
        b = _profile(full_name="Johnathan Doe")
        result = ENGINE.merge(a, b)
        assert result.merged_profile.full_name == "Johnathan Doe"

    def test_both_none_returns_none(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile.full_name is None

    def test_identical_names_deduplicated(self) -> None:
        a = _profile(full_name="Alice Smith")
        b = _profile(full_name="Alice Smith")
        result = ENGINE.merge(a, b)
        assert result.merged_profile.full_name == "Alice Smith"
        d = result.field_decisions.get("full_name")
        assert d.reason == MergeReason.DEDUPLICATION

    def test_case_insensitive_dedup(self) -> None:
        # Same name, different casing → treated as identical → résumé form kept.
        a = _profile(full_name="alice smith")
        b = _profile(full_name="Alice Smith")
        result = ENGINE.merge(a, b)
        assert result.merged_profile.full_name == "Alice Smith"
        assert result.field_decisions["full_name"].reason == MergeReason.DEDUPLICATION

    def test_reason_only_value_when_one_side_present(self) -> None:
        a = _profile(full_name=None)
        b = _profile(full_name="Solo Name")
        result = ENGINE.merge(a, b)
        assert result.field_decisions["full_name"].reason == MergeReason.ONLY_VALUE


# ===========================================================================
# headline
# ===========================================================================

class TestMergeHeadline:
    def test_resume_wins_on_conflict(self) -> None:
        a = _profile(headline="Software Engineer")
        b = _profile(headline="Senior Software Engineer")
        result = ENGINE.merge(a, b)
        assert result.merged_profile.headline == "Senior Software Engineer"

    def test_decision_records_discarded(self) -> None:
        a = _profile(headline="Software Engineer")
        b = _profile(headline="Senior Software Engineer")
        result = ENGINE.merge(a, b)
        d = result.field_decisions["headline"]
        assert d.reason == MergeReason.RESUME_PRIORITY
        assert d.discarded_value == "Software Engineer"

    def test_fallback_to_ats_when_resume_absent(self) -> None:
        a = _profile(headline="Software Engineer")
        b = _profile(headline=None)
        result = ENGINE.merge(a, b)
        assert result.merged_profile.headline == "Software Engineer"

    def test_none_when_both_absent(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile.headline is None

    def test_identical_headlines_deduplicated(self) -> None:
        a = _profile(headline="Engineer")
        b = _profile(headline="Engineer")
        result = ENGINE.merge(a, b)
        d = result.field_decisions["headline"]
        assert d.reason == MergeReason.DEDUPLICATION


# ===========================================================================
# years_experience
# ===========================================================================

class TestMergeYearsExperience:
    def test_larger_value_selected(self) -> None:
        a = _profile(years_experience=2.0)
        b = _profile(years_experience=4.0)
        result = ENGINE.merge(a, b)
        assert result.merged_profile.years_experience == 4.0

    def test_larger_value_selected_ats_higher(self) -> None:
        a = _profile(years_experience=6.0)
        b = _profile(years_experience=3.5)
        result = ENGINE.merge(a, b)
        assert result.merged_profile.years_experience == 6.0

    def test_decision_reason_larger_value(self) -> None:
        a = _profile(years_experience=2.0)
        b = _profile(years_experience=4.0)
        result = ENGINE.merge(a, b)
        d = result.field_decisions["years_experience"]
        assert d.reason == MergeReason.LARGER_VALUE
        assert d.chosen_value == 4.0

    def test_uses_available_when_one_absent(self) -> None:
        a = _profile(years_experience=5.0)
        b = _profile(years_experience=None)
        result = ENGINE.merge(a, b)
        assert result.merged_profile.years_experience == 5.0

    def test_none_when_both_absent(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile.years_experience is None

    def test_equal_values_returns_that_value(self) -> None:
        a = _profile(years_experience=3.0)
        b = _profile(years_experience=3.0)
        result = ENGINE.merge(a, b)
        assert result.merged_profile.years_experience == 3.0


# ===========================================================================
# emails
# ===========================================================================

class TestMergeEmails:
    def test_union_distinct_emails(self) -> None:
        a = _profile(emails=["alice@a.com"])
        b = _profile(emails=["bob@b.com"])
        result = ENGINE.merge(a, b)
        assert set(result.merged_profile.emails) == {"alice@a.com", "bob@b.com"}

    def test_case_insensitive_dedup(self) -> None:
        a = _profile(emails=["John@Gmail.COM"])
        b = _profile(emails=["john@gmail.com"])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.emails) == 1
        assert result.merged_profile.emails[0] == "john@gmail.com"

    def test_preserves_order_a_first(self) -> None:
        a = _profile(emails=["first@a.com"])
        b = _profile(emails=["second@b.com"])
        result = ENGINE.merge(a, b)
        assert result.merged_profile.emails[0] == "first@a.com"

    def test_empty_both_returns_empty(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile.emails == []

    def test_empty_one_side(self) -> None:
        a = _profile(emails=["only@a.com"])
        b = _profile(emails=[])
        result = ENGINE.merge(a, b)
        assert result.merged_profile.emails == ["only@a.com"]

    def test_multiple_emails_unioned(self) -> None:
        a = _profile(emails=["a@x.com", "b@x.com"])
        b = _profile(emails=["b@x.com", "c@x.com"])
        result = ENGINE.merge(a, b)
        assert set(result.merged_profile.emails) == {"a@x.com", "b@x.com", "c@x.com"}

    def test_decision_reason_union(self) -> None:
        a = _profile(emails=["x@y.com"])
        b = _profile(emails=["z@w.com"])
        result = ENGINE.merge(a, b)
        d = result.field_decisions["emails"]
        assert d.reason == MergeReason.UNION


# ===========================================================================
# phones
# ===========================================================================

class TestMergePhones:
    def test_union_distinct_phones(self) -> None:
        a = _profile(phones=["+91 9876543210"])
        b = _profile(phones=["+1 4155550100"])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.phones) == 2

    def test_digit_dedup_same_number_different_format(self) -> None:
        a = _profile(phones=["+91 98765 43210"])
        b = _profile(phones=["+919876543210"])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.phones) == 1

    def test_empty_both_returns_empty(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile.phones == []

    def test_first_representation_preserved(self) -> None:
        """The formatted phone from profile_a is kept when digits match."""
        a = _profile(phones=["+91 9876543210"])
        b = _profile(phones=["9876543210"])
        result = ENGINE.merge(a, b)
        assert result.merged_profile.phones[0] == "+91 9876543210"

    def test_decision_reason_union(self) -> None:
        a = _profile(phones=["+91 9876543210"])
        b = _profile(phones=["+1 4155550100"])
        result = ENGINE.merge(a, b)
        d = result.field_decisions["phones"]
        assert d.reason == MergeReason.UNION


# ===========================================================================
# links
# ===========================================================================

class TestMergeLinks:
    def test_resume_linkedin_wins_on_conflict(self) -> None:
        a = _profile(links=Links(linkedin="https://linkedin.com/in/old-profile"))
        b = _profile(links=Links(linkedin="https://linkedin.com/in/new-profile"))
        result = ENGINE.merge(a, b)
        link_strs = [str(lk) for lk in result.merged_profile.links]
        assert any("new-profile" in lk for lk in link_strs)
        assert not any("old-profile" in lk for lk in link_strs)

    def test_keeps_only_available_linkedin(self) -> None:
        a = _profile(links=Links())
        b = _profile(links=Links(linkedin="https://linkedin.com/in/johndoe"))
        result = ENGINE.merge(a, b)
        link_strs = [str(lk) for lk in result.merged_profile.links]
        assert any("johndoe" in lk for lk in link_strs)

    def test_keeps_github_from_ats_when_resume_absent(self) -> None:
        a = _profile(links=Links(github="https://github.com/johndoe"))
        b = _profile(links=Links())
        result = ENGINE.merge(a, b)
        link_strs = [str(lk) for lk in result.merged_profile.links]
        assert any("github.com" in lk for lk in link_strs)

    def test_both_linkedin_and_github_kept(self) -> None:
        a = _profile(links=Links(linkedin="https://linkedin.com/in/alice"))
        b = _profile(links=Links(github="https://github.com/alice"))
        result = ENGINE.merge(a, b)
        link_strs = [str(lk) for lk in result.merged_profile.links]
        assert any("linkedin.com" in lk for lk in link_strs)
        assert any("github.com" in lk for lk in link_strs)

    def test_empty_both_returns_empty(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile.links == Links()

    def test_decision_recorded_for_conflict(self) -> None:
        a = _profile(links=Links(linkedin="https://linkedin.com/in/old"))
        b = _profile(links=Links(linkedin="https://linkedin.com/in/new"))
        result = ENGINE.merge(a, b)
        decisions = {d.field_name: d for d in result.merge_decisions}
        assert "links.linkedin" in decisions
        assert decisions["links.linkedin"].reason == MergeReason.RESUME_PRIORITY


# ===========================================================================
# location
# ===========================================================================

class TestMergeLocation:
    def test_complement_merge_different_fields(self) -> None:
        a = _profile(location=Location(city="Bangalore"))
        b = _profile(location=Location(country="IN"))
        result = ENGINE.merge(a, b)
        loc = result.merged_profile.location
        assert loc is not None
        assert loc.city == "Bangalore"
        assert loc.country == "IN"

    def test_resume_wins_on_conflict(self) -> None:
        a = _profile(location=Location(city="Mumbai"))
        b = _profile(location=Location(city="Bangalore"))
        result = ENGINE.merge(a, b)
        assert result.merged_profile.location.city == "Bangalore"  # type: ignore

    def test_conflict_recorded(self) -> None:
        a = _profile(location=Location(city="Mumbai"))
        b = _profile(location=Location(city="Bangalore"))
        result = ENGINE.merge(a, b)
        decisions = {d.field_name: d for d in result.merge_decisions}
        assert "location.city" in decisions
        d = decisions["location.city"]
        assert d.reason == MergeReason.RESUME_PRIORITY
        assert d.discarded_value == "Mumbai"

    def test_none_a_returns_b(self) -> None:
        b = _profile(location=Location(city="Delhi"))
        result = ENGINE.merge(_profile(), b)
        assert result.merged_profile.location.city == "Delhi"  # type: ignore

    def test_none_b_returns_a(self) -> None:
        a = _profile(location=Location(region="Karnataka"))
        result = ENGINE.merge(a, _profile())
        assert result.merged_profile.location.region == "Karnataka"  # type: ignore

    def test_both_none_returns_none(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile.location is None

    def test_all_fields_merged(self) -> None:
        a = _profile(location=Location(city="X", region="S1"))
        b = _profile(location=Location(country="IN", postal_code="560001"))
        result = ENGINE.merge(a, b)
        loc = result.merged_profile.location
        assert loc.city == "X"
        assert loc.region == "S1"
        assert loc.country == "IN"
        assert loc.postal_code == "560001"

    def test_decision_field_level_merge(self) -> None:
        a = _profile(location=Location(city="X"))
        b = _profile(location=Location(country="IN"))
        result = ENGINE.merge(a, b)
        d = result.field_decisions.get("location")
        assert d is not None
        assert d.reason == MergeReason.FIELD_LEVEL_MERGE


# ===========================================================================
# skills
# ===========================================================================

class TestMergeSkills:
    def test_union_distinct_skills(self) -> None:
        a = _profile(skills=[_skill("Python")])
        b = _profile(skills=[_skill("React", "resume")])
        result = ENGINE.merge(a, b)
        names = {s.name for s in result.merged_profile.skills}
        assert "Python" in names
        assert "React" in names

    def test_dedup_by_canonical_name(self) -> None:
        a = _profile(skills=[_skill("Python", "ats")])
        b = _profile(skills=[_skill("Python", "resume")])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.skills) == 1

    def test_dedup_is_case_insensitive(self) -> None:
        a = _profile(skills=[_skill("python")])
        b = _profile(skills=[_skill("Python")])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.skills) == 1

    def test_merged_skill_gets_merged_source_tag(self) -> None:
        a = _profile(skills=[_skill("Python", "ats")])
        b = _profile(skills=[_skill("Python", "resume")])
        result = ENGINE.merge(a, b)
        assert set(result.merged_profile.skills[0].sources) == {"ats", "resume"}

    def test_resume_version_preferred_for_level(self) -> None:
        ats_skill = Skill(name="Python", source="ats", level=SkillLevel.UNKNOWN)
        res_skill  = Skill(name="Python", source="resume", level=SkillLevel.ADVANCED)
        a = _profile(skills=[ats_skill])
        b = _profile(skills=[res_skill])
        result = ENGINE.merge(a, b)
        assert result.merged_profile.skills[0].level == SkillLevel.ADVANCED

    def test_empty_both_returns_empty(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile.skills == []

    def test_skills_only_in_a_preserved(self) -> None:
        a = _profile(skills=[_skill("Go")])
        b = _profile(skills=[])
        result = ENGINE.merge(a, b)
        assert any(s.name == "Go" for s in result.merged_profile.skills)

    def test_skills_only_in_b_preserved(self) -> None:
        a = _profile(skills=[])
        b = _profile(skills=[_skill("Rust", "resume")])
        result = ENGINE.merge(a, b)
        assert any(s.name == "Rust" for s in result.merged_profile.skills)

    def test_decision_reason_union(self) -> None:
        a = _profile(skills=[_skill("Python")])
        b = _profile(skills=[_skill("React", "resume")])
        result = ENGINE.merge(a, b)
        d = result.field_decisions["skills"]
        assert d.reason == MergeReason.UNION

    def test_years_of_experience_preserved_from_resume(self) -> None:
        ats_skill  = Skill(name="Python", source="ats",    years_of_experience=None)
        res_skill  = Skill(name="Python", source="resume", years_of_experience=3.0)
        a = _profile(skills=[ats_skill])
        b = _profile(skills=[res_skill])
        result = ENGINE.merge(a, b)
        assert result.merged_profile.skills[0].years_of_experience == 3.0


# ===========================================================================
# experience
# ===========================================================================

class TestMergeExperience:
    def test_union_distinct_entries(self) -> None:
        a = _profile(experience=[_exp("Eng", "Acme", "2020-01")])
        b = _profile(experience=[_exp("Dev", "Beta", "2021-06", source="resume")])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.experience) == 2

    def test_dedup_on_company_title_start_year(self) -> None:
        exp_a = _exp("Engineer", "Acme", "2020-01", source="ats")
        exp_b = _exp("Engineer", "Acme", date(2020, 3, 15), source="resume")
        # Different start month/day but SAME year → same key → deduplicated.
        a = _profile(experience=[exp_a])
        b = _profile(experience=[exp_b])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.experience) == 1

    def test_resume_version_kept_after_dedup(self) -> None:
        exp_a = _exp("Engineer", "Acme", "2020-01", source="ats")
        exp_b = _exp("Engineer", "Acme", "2020-01", source="resume")
        a = _profile(experience=[exp_a])
        b = _profile(experience=[exp_b])
        result = ENGINE.merge(a, b)
        assert result.merged_profile.experience[0].source == "resume"

    def test_different_companies_both_kept(self) -> None:
        a = _profile(experience=[_exp("Eng", "CompanyA", "2019-01")])
        b = _profile(experience=[_exp("Eng", "CompanyB", "2019-01", source="resume")])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.experience) == 2

    def test_different_titles_both_kept(self) -> None:
        a = _profile(experience=[_exp("Junior Eng", "Acme", "2019-01")])
        b = _profile(experience=[_exp("Senior Eng", "Acme", "2019-01", source="resume")])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.experience) == 2

    def test_sorted_descending_by_start_date(self) -> None:
        a = _profile(experience=[
            _exp("Old Role", "Corp", date(2015, 1, 1)),
        ])
        b = _profile(experience=[
            _exp("New Role", "Corp", "2022-01", source="resume"),
        ])
        result = ENGINE.merge(a, b)
        exp = result.merged_profile.experience
        assert exp[0].start > exp[1].start  # type: ignore

    def test_empty_both_returns_empty(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile.experience == []

    def test_decision_reason_union(self) -> None:
        a = _profile(experience=[_exp("Eng", "A", "2020-01")])
        b = _profile(experience=[_exp("Dev", "B", "2021-01", source="resume")])
        result = ENGINE.merge(a, b)
        d = result.field_decisions["experience"]
        assert d.reason == MergeReason.UNION


# ===========================================================================
# education
# ===========================================================================

class TestMergeEducation:
    def test_union_distinct_entries(self) -> None:
        a = _profile(education=[_edu("MIT", EducationDegree.BACHELOR)])
        b = _profile(education=[_edu("Stanford", EducationDegree.MASTER, source="resume")])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.education) == 2

    def test_dedup_on_institution_degree_end_year(self) -> None:
        edu_a = _edu("MIT", EducationDegree.BACHELOR, end="2018")
        edu_b = _edu("MIT", EducationDegree.BACHELOR, end="2018", source="resume")
        # Same institution + degree + end year → deduplicated.
        a = _profile(education=[edu_a])
        b = _profile(education=[edu_b])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.education) == 1

    def test_resume_version_kept_after_dedup(self) -> None:
        edu_a = _edu("MIT", EducationDegree.BACHELOR, end="2018-05", source="ats")
        edu_b = _edu("MIT", EducationDegree.BACHELOR, end="2018-05", source="resume", gpa=9.0)
        a = _profile(education=[edu_a])
        b = _profile(education=[edu_b])
        result = ENGINE.merge(a, b)
        assert result.merged_profile.education[0].source == "resume"
        assert result.merged_profile.education[0].gpa == 9.0

    def test_different_degrees_both_kept(self) -> None:
        a = _profile(education=[_edu("MIT", EducationDegree.BACHELOR)])
        b = _profile(education=[_edu("MIT", EducationDegree.MASTER, source="resume")])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.education) == 2

    def test_different_institutions_both_kept(self) -> None:
        a = _profile(education=[_edu("MIT", EducationDegree.BACHELOR)])
        b = _profile(education=[_edu("Harvard", EducationDegree.BACHELOR, source="resume")])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.education) == 2

    def test_empty_both_returns_empty(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile.education == []

    def test_decision_reason_union(self) -> None:
        a = _profile(education=[_edu("MIT")])
        b = _profile(education=[_edu("Stanford", source="resume")])
        result = ENGINE.merge(a, b)
        d = result.field_decisions["education"]
        assert d.reason == MergeReason.UNION


# ===========================================================================
# provenance
# ===========================================================================

class TestMergeProvenance:
    def test_union_of_all_provenance(self) -> None:
        a = _profile(provenance=[_prov("full_name", "ats")])
        b = _profile(provenance=[_prov("full_name", "resume")])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.provenance) == 2

    def test_provenance_never_discarded(self) -> None:
        prov_a = [_prov(f"field_{i}", "ats") for i in range(5)]
        prov_b = [_prov(f"field_{i}", "resume") for i in range(5)]
        a = _profile(provenance=prov_a)
        b = _profile(provenance=prov_b)
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.provenance) == 10

    def test_order_a_then_b(self) -> None:
        prov_a = _prov("first", "ats")
        prov_b = _prov("second", "resume")
        a = _profile(provenance=[prov_a])
        b = _profile(provenance=[prov_b])
        result = ENGINE.merge(a, b)
        assert result.merged_profile.provenance[0].source == "ats"
        assert result.merged_profile.provenance[1].source == "resume"

    def test_empty_both_returns_empty(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile.provenance == []


# ===========================================================================
# MergeDecision structure
# ===========================================================================

class TestMergeDecisions:
    def test_every_field_has_a_decision(self) -> None:
        """At minimum the engine records a decision for every top-level field."""
        result = ENGINE.merge(_profile(), _profile())
        field_names = {d.field_name for d in result.merge_decisions}
        # All required fields must appear.
        required = {"full_name", "headline", "years_experience", "emails", "phones", "skills"}
        assert required.issubset(field_names)

    def test_decision_is_frozen(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        d = result.merge_decisions[0]
        with pytest.raises(Exception):
            d.field_name = "hacked"  # type: ignore

    def test_all_reasons_are_merge_reason_enum(self) -> None:
        result = ENGINE.merge(
            _profile(full_name="A", emails=["a@x.com"]),
            _profile(full_name="B", emails=["b@y.com"]),
        )
        for d in result.merge_decisions:
            assert isinstance(d.reason, MergeReason)

    def test_source_labels_in_decisions(self) -> None:
        engine = MergeEngine(profile_a_label="myats", profile_b_label="myresume")
        result = engine.merge(
            _profile(full_name="A"),
            _profile(full_name="B"),
        )
        d = result.field_decisions["full_name"]
        assert d.source_a_label == "myats"
        assert d.source_b_label == "myresume"


# ===========================================================================
# MergeResult helpers
# ===========================================================================

class TestMergeResult:
    def test_conflict_count_no_conflicts(self) -> None:
        a = _profile(full_name="Alice")
        b = _profile(full_name=None)  # no conflict
        result = ENGINE.merge(a, b)
        # full_name has no discarded_value because only one side had data.
        d = result.field_decisions.get("full_name")
        assert d.discarded_value is None

    def test_conflict_count_with_conflicts(self) -> None:
        a = _profile(full_name="Alice", headline="Old")
        b = _profile(full_name="Bob",   headline="New")
        result = ENGINE.merge(a, b)
        assert result.conflict_count >= 2

    def test_field_decisions_dict_keyed_by_field_name(self) -> None:
        result = ENGINE.merge(_profile(full_name="A"), _profile(full_name="B"))
        fd = result.field_decisions
        assert "full_name" in fd
        assert isinstance(fd["full_name"], MergeDecision)

    def test_profile_a_source_label(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.profile_a_source is not None

    def test_profile_b_source_label(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.profile_b_source is not None


# ===========================================================================
# Robustness (None fields, empty inputs)
# ===========================================================================

class TestMergeRobustness:
    def test_both_profiles_empty_does_not_crash(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile is not None

    def test_profile_a_all_none(self) -> None:
        b = _profile(
            full_name="Bob",
            emails=["bob@x.com"],
            phones=["+1 5550100"],
            skills=[_skill("Python", "resume")],
        )
        result = ENGINE.merge(_profile(), b)
        assert result.merged_profile.full_name == "Bob"
        assert result.merged_profile.emails == ["bob@x.com"]

    def test_profile_b_all_none(self) -> None:
        a = _profile(
            full_name="Alice",
            emails=["alice@x.com"],
        )
        result = ENGINE.merge(a, _profile())
        assert result.merged_profile.full_name == "Alice"

    def test_years_experience_none_both_sides(self) -> None:
        result = ENGINE.merge(_profile(), _profile())
        assert result.merged_profile.years_experience is None

    def test_location_with_all_none_fields(self) -> None:
        # Both sides have Location(raw=None) — all sub-fields None.
        a = _profile(location=Location())
        b = _profile(location=Location())
        result = ENGINE.merge(a, b)
        loc = result.merged_profile.location
        assert loc is not None
        assert loc.city is None

    def test_large_skill_list_no_crash(self) -> None:
        skills = [_skill(f"Skill{i}") for i in range(100)]
        a = _profile(skills=skills)
        b = _profile(skills=skills[:50])
        result = ENGINE.merge(a, b)
        assert len(result.merged_profile.skills) == 100

    def test_large_experience_no_crash(self) -> None:
        exps = [_exp(f"Role{i}", "Corp", date(2000 + i, 1, 1)) for i in range(20)]
        a = _profile(experience=exps)
        b = _profile(experience=exps)
        result = ENGINE.merge(a, b)
        # All are duplicates → should collapse to 20.
        assert len(result.merged_profile.experience) == 20


# ===========================================================================
# End-to-end integration test
# ===========================================================================

class TestMergeEngineEndToEnd:
    """
    Realistic merge of an ATS profile and a résumé profile for the same
    candidate.  The ATS has structured scalar data; the résumé has more skills
    and a richer headline.
    """

    @pytest.fixture()
    def ats_profile(self) -> CandidateProfile:
        return CandidateProfile(
            full_name="John Doe",
            headline="Software Engineer",
            years_experience=4.0,
            emails=["john@gmail.com"],
            phones=["+91 9876543210"],
            location=Location(city="Bangalore", country="IN"),
            skills=[
                Skill(name="Python", sources=["ats"]),
                Skill(name="Docker", sources=["ats"]),
            ],
            experience=[
                Experience(
                    title="Software Engineer",
                    company="Acme Corp",
                    start="2019-01",
                    is_current=True,
                    source="ats",
                ),
            ],
            education=[
                Education(
                    institution="IIT Bombay",
                    degree=EducationDegree.BACHELOR,
                    end_year="2018-05",
                    source="ats",
                ),
            ],
            links=Links(linkedin="https://linkedin.com/in/johndoe"),
            provenance=[ProvenanceRecord(field="full_name", source="ats")],
        )

    @pytest.fixture()
    def resume_profile(self) -> CandidateProfile:
        return CandidateProfile(
            full_name="Johnathan Doe",
            headline="Senior Software Engineer",
            years_experience=6.0,
            emails=["john@gmail.com", "johndoe@work.io"],
            phones=["+91 9876543210", "+91 8765432109"],
            location=Location(city="Bangalore", region="Karnataka", country="IN"),
            skills=[
                Skill(name="Python", sources=["resume"]),
                Skill(name="React",  sources=["resume"]),
                Skill(name="AWS",    sources=["resume"]),
            ],
            experience=[
                Experience(
                    title="Senior Software Engineer",
                    company="Acme Corp",
                    start="2021-06",
                    is_current=True,
                    source="resume",
                ),
                Experience(
                    title="Software Engineer",
                    company="Acme Corp",
                    start="2019-01",
                    end_year="2021-05",
                    source="resume",
                ),
            ],
            education=[
                Education(
                    institution="IIT Bombay",
                    degree=EducationDegree.BACHELOR,
                    end_year="2018-05",
                    gpa=8.9,
                    source="resume",
                ),
            ],
            links=Links(
                linkedin="https://linkedin.com/in/johndoe",
                github="https://github.com/johndoe",
            ),
            provenance=[
                ProvenanceRecord(field="full_name", source="resume"),
                ProvenanceRecord(field="skills[0]", source="resume"),
            ],
        )

    def test_name_is_resume_version(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        assert result.merged_profile.full_name == "Johnathan Doe"

    def test_headline_is_resume_version(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        assert result.merged_profile.headline == "Senior Software Engineer"

    def test_years_experience_is_max(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        assert result.merged_profile.years_experience == 6.0

    def test_emails_deduplicated(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        # john@gmail.com appears in both → deduped to 1.
        assert len(result.merged_profile.emails) == 2
        assert "john@gmail.com" in result.merged_profile.emails

    def test_phones_deduplicated(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        # +91 9876543210 in both → deduped.
        assert len(result.merged_profile.phones) == 2

    def test_location_merged_field_level(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        loc = result.merged_profile.location
        assert loc.city == "Bangalore"
        assert loc.region == "Karnataka"
        assert loc.country == "IN"

    def test_skills_unioned_and_deduplicated(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        skill_names = {s.name for s in result.merged_profile.skills}
        # Python from both → merged=1; Docker from ATS; React, AWS from resume.
        assert "Python" in skill_names
        assert "Docker" in skill_names
        assert "React" in skill_names
        assert "AWS" in skill_names
        # Python should NOT appear twice.
        python_skills = [s for s in result.merged_profile.skills if s.name == "Python"]
        assert len(python_skills) == 1
        assert set(python_skills[0].sources) == {"ats", "resume"}

    def test_experience_correct_count(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        # ATS has 1; resume has 2; they share same company+title+start_year for
        # "Software Engineer @ Acme Corp 2019" → deduped → 2 unique entries.
        assert len(result.merged_profile.experience) == 2

    def test_education_gpa_from_resume(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        assert len(result.merged_profile.education) == 1
        assert result.merged_profile.education[0].gpa == 8.9

    def test_both_links_present(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        link_strs = [str(lk) for lk in result.merged_profile.links]
        assert any("linkedin.com" in lk for lk in link_strs)
        assert any("github.com" in lk for lk in link_strs)

    def test_all_provenance_preserved(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        # 1 from ATS + 2 from resume = 3 total.
        assert len(result.merged_profile.provenance) == 3

    def test_conflict_count_matches_expected(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        # At least full_name and headline are conflicts.
        assert result.conflict_count >= 2

    def test_name_conflict_decision(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        d = result.field_decisions["full_name"]
        assert d.reason == MergeReason.RESUME_PRIORITY
        assert d.chosen_value == "Johnathan Doe"
        assert d.discarded_value == "John Doe"

    def test_merge_result_sources_correct(self, ats_profile, resume_profile) -> None:
        result = ENGINE.merge(ats_profile, resume_profile)
        assert result.profile_a_source == "ats"
        assert result.profile_b_source == "resume"
