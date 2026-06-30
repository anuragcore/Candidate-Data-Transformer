"""
tests/test_projection_engine.py — Tests for the Projection Engine.
"""

from __future__ import annotations

from typing import Any
import pytest

from src.models import (
    CandidateProfile,
    ProjectionConfig,
    Skill,
    Location,
    Experience,
    Education,
    ProvenanceRecord,
)
from src.models.config import ProjectionField, OnMissingStrategy
from src.projector import ProjectionEngine, ProjectionError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_projection(profile: CandidateProfile, fields: list[ProjectionField], **kwargs: Any) -> dict[str, Any]:
    config = ProjectionConfig(name="test", fields=fields, **kwargs)
    engine = ProjectionEngine(config=config)
    return engine.project(profile)


def _profile(**kwargs: Any) -> CandidateProfile:
    return CandidateProfile(**kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFieldSelectionAndRename:
    def test_simple_field_selection(self) -> None:
        p = _profile(full_name="John Doe")
        f = [ProjectionField(path="full_name", **{"from": "full_name"})]
        out = _run_projection(p, f)
        assert out == {"full_name": "John Doe"}

    def test_field_rename(self) -> None:
        p = _profile(emails=["john@gmail.com"])
        f = [ProjectionField(path="primary_email", **{"from": "emails[0]"})]
        out = _run_projection(p, f)
        assert out == {"primary_email": "john@gmail.com"}

    def test_nested_output_path(self) -> None:
        p = _profile(full_name="John Doe")
        f = [ProjectionField(path="candidate.contact.name", **{"from": "full_name"})]
        out = _run_projection(p, f)
        assert out == {"candidate": {"contact": {"name": "John Doe"}}}


class TestPathResolution:
    def test_dot_notation(self) -> None:
        p = _profile(location=Location(city="Bangalore"))
        f = [ProjectionField(path="city", **{"from": "location.city"})]
        out = _run_projection(p, f)
        assert out == {"city": "Bangalore"}

    def test_bracket_notation_list(self) -> None:
        p = _profile(skills=[Skill(name="Python")])
        f = [ProjectionField(path="skill", **{"from": "skills[0].name"})]
        out = _run_projection(p, f)
        assert out == {"skill": "Python"}

    def test_out_of_bounds_index_returns_null(self) -> None:
        p = _profile(skills=[])
        f = [ProjectionField(path="skill", **{"from": "skills[0].name"})]
        out = _run_projection(p, f)
        assert out == {"skill": None}

    def test_missing_attribute_returns_null(self) -> None:
        p = _profile(location=Location(city="Bangalore"))
        f = [ProjectionField(path="state", **{"from": "location.state"})]
        out = _run_projection(p, f)
        assert out == {"state": None}

    def test_nested_attribute_on_none_returns_null(self) -> None:
        p = _profile(location=None)
        f = [ProjectionField(path="city", **{"from": "location.city"})]
        out = _run_projection(p, f)
        assert out == {"city": None}

    def test_malformed_path_raises_error(self) -> None:
        p = _profile()
        f = [ProjectionField(path="test", **{"from": "skills[a]"})]
        with pytest.raises(ProjectionError):
            _run_projection(p, f)


class TestMissingStrategies:
    def test_null_strategy(self) -> None:
        p = _profile()
        f = [ProjectionField(path="phone", **{"from": "phones[0]", "on_missing": OnMissingStrategy.NULL})]
        out = _run_projection(p, f)
        assert out == {"phone": None}

    def test_omit_strategy(self) -> None:
        p = _profile()
        f = [ProjectionField(path="phone", **{"from": "phones[0]", "on_missing": OnMissingStrategy.OMIT})]
        out = _run_projection(p, f)
        assert "phone" not in out

    def test_default_strategy(self) -> None:
        p = _profile()
        f = [ProjectionField(path="phone", **{"from": "phones[0]", "on_missing": OnMissingStrategy.DEFAULT, "default_value": "N/A"})]
        out = _run_projection(p, f)
        assert out == {"phone": "N/A"}

    def test_error_strategy_raises(self) -> None:
        p = _profile()
        f = [ProjectionField(path="phone", **{"from": "phones[0]", "on_missing": OnMissingStrategy.RAISE})]
        with pytest.raises(ProjectionError):
            _run_projection(p, f)

    def test_required_field_raises_when_missing_and_error_strategy(self) -> None:
        p = _profile()
        f = [ProjectionField(path="name", **{"from": "full_name", "required": True, "on_missing": OnMissingStrategy.RAISE})]
        with pytest.raises(ProjectionError, match="Required field missing"):
            _run_projection(p, f)

    def test_required_field_does_not_raise_if_value_present(self) -> None:
        p = _profile(full_name="John Doe")
        f = [ProjectionField(path="name", **{"from": "full_name", "required": True, "on_missing": OnMissingStrategy.RAISE})]
        out = _run_projection(p, f)
        assert out == {"name": "John Doe"}


class TestConfigFlags:
    def test_include_provenance(self) -> None:
        prov = ProvenanceRecord(field="full_name", source="ats")
        p = _profile(full_name="John Doe", provenance=[prov])
        f = [ProjectionField(path="name", **{"from": "full_name"})]
        out = _run_projection(p, f, include_provenance=True)
        assert "name" in out
        assert "provenance" in out
        assert len(out["provenance"]) == 1
        assert out["provenance"][0]["source"] == "ats"

    def test_exclude_provenance(self) -> None:
        prov = ProvenanceRecord(field="full_name", source="ats")
        p = _profile(full_name="John Doe", provenance=[prov])
        f = [ProjectionField(path="name", **{"from": "full_name"})]
        out = _run_projection(p, f, include_provenance=False)
        assert "provenance" not in out

    def test_strip_null_fields(self) -> None:
        p = _profile()
        f = [
            ProjectionField(path="name", **{"from": "full_name", "on_missing": OnMissingStrategy.NULL}),
            ProjectionField(path="nested.missing", **{"from": "location.city", "on_missing": OnMissingStrategy.NULL}),
            ProjectionField(path="nested.present", **{"from": "location.city", "on_missing": OnMissingStrategy.DEFAULT, "default_value": "Val"})
        ]
        out = _run_projection(p, f, strip_null_fields=True)
        assert "name" not in out
        assert "missing" not in out.get("nested", {})
        assert out["nested"]["present"] == "Val"
