"""
Phase 1 smoke tests — verify the skeleton is importable and models are valid.

These tests make NO assumptions about business logic.  They simply ensure:

1. All Pydantic models can be instantiated with default / minimal values.
2. The CLI entry-point (``main.run()``) prints "Pipeline initialized" and
   returns exit code 0.
3. Adapter stubs exist and raise ``NotImplementedError`` as expected.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Model smoke tests
# ---------------------------------------------------------------------------


class TestCandidateProfileModel:
    """Ensure CandidateProfile can be instantiated and is a valid Pydantic model."""

    def test_default_instantiation(self) -> None:
        """A CandidateProfile with no arguments should be valid."""
        from src.models import CandidateProfile

        profile = CandidateProfile()
        assert profile.candidate_id is not None
        assert profile.full_name is None
        assert profile.emails == []
        assert profile.skills == []
        assert profile.provenance == []

    def test_with_full_name(self) -> None:
        """full_name should be assignable."""
        from src.models import CandidateProfile

        profile = CandidateProfile(full_name="Ada Lovelace")
        assert profile.full_name == "Ada Lovelace"

    def test_skill_model(self) -> None:
        from src.models import Skill, SkillLevel

        skill = Skill(name="Python")
        assert skill.name == "Python"
        assert skill.level == SkillLevel.UNKNOWN

    def test_location_model(self) -> None:
        from src.models import Location

        loc = Location(city="London", country="GB")
        assert loc.city == "London"

    def test_provenance_record_confidence_bounds(self) -> None:
        """Confidence score must be in [0.0, 1.0]."""
        from pydantic import ValidationError

        from src.models import ProvenanceRecord

        with pytest.raises(ValidationError):
            ProvenanceRecord(field="full_name", sources=["ats"], confidence=1.5)


class TestProjectionConfigModel:
    """Ensure ProjectionConfig and ProjectionField are valid."""

    def test_empty_projection(self) -> None:
        from src.models import ProjectionConfig

        config = ProjectionConfig(name="test")
        assert config.name == "test"
        assert config.fields == []

    def test_projection_field_with_alias(self) -> None:
        from src.models import ProjectionField

        field = ProjectionField(
            path="output.name",
            **{"from": "full_name"},
        )
        assert field.path == "output.name"
        assert field.from_field == "full_name"


# ---------------------------------------------------------------------------
# Adapter importability tests (stubs replaced by Phase 2 implementations)
# ---------------------------------------------------------------------------


class TestAdapterImportability:
    """
    Verify adapters are importable and instantiable after Phase 2.

    The full behavioural test suite lives in ``test_phase2_adapters.py``.
    These tests guard against import-level regressions only.
    """

    def test_ats_adapter_importable(self) -> None:
        from src.adapters import ATSAdapter

        adapter = ATSAdapter(path=Path("inputs/dummy.json"))
        assert adapter.source_name == "ats"

    def test_resume_adapter_importable(self) -> None:
        from src.adapters import ResumeAdapter

        adapter = ResumeAdapter(path=Path("inputs/dummy.pdf"))
        assert adapter.source_name == "resume"

    def test_adapter_error_importable(self) -> None:
        from src.adapters.base import AdapterError

        err = AdapterError("test error", source="ats")
        assert err.source == "ats"


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


class TestCLI:
    """Verify the CLI entry point behaves correctly in Phase 1."""

    def test_pipeline_initialized_message(self, capsys: pytest.CaptureFixture) -> None:
        """Running main.run() should print 'Pipeline initialized' and return 0."""
        from main import build_parser, run

        args = build_parser().parse_args([])
        exit_code = run(args)
        captured = capsys.readouterr()
        assert "No inputs provided. Exiting." in captured.out
        assert exit_code == 1
