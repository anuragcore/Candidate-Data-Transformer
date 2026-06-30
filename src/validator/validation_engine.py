"""
ValidationEngine — post-merge profile validation engine (stub).

The ``ValidationEngine`` verifies that a merged :class:`~src.models.CandidateProfile`
meets all business rules and data quality thresholds **before** it is
projected into a consumer-specific output.

Validation is separated from Pydantic schema validation (which happens at
construction time) and focuses on **semantic** / **business-rule** validation:
for example, "a candidate must have at least one email address" or
"years_experience must not exceed 60".

Current status: **Phase 1 stub** — no validation logic implemented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models import CandidateProfile


@dataclass
class ValidationResult:
    """
    The outcome of a validation run.

    Attributes
    ----------
    is_valid:
        ``True`` if the profile passed all validation rules.
    errors:
        List of human-readable error messages for failed rules.
    warnings:
        List of human-readable warning messages for near-miss conditions.
    """

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ValidationEngine:
    """
    Runs a suite of semantic validation rules against a ``CandidateProfile``.

    Usage (planned)
    ---------------
    ::

        engine = ValidationEngine()
        result = engine.validate(merged_profile)
        if not result.is_valid:
            raise ValueError(result.errors)
    """

    def validate(self, profile: CandidateProfile) -> ValidationResult:
        """
        Run all registered validation rules against ``profile``.

        Parameters
        ----------
        profile:
            The merged :class:`~src.models.CandidateProfile` to validate.

        Returns
        -------
        ValidationResult
            A result object indicating pass/fail along with any error and
            warning messages.

        TODO (Phase 5):
        ---------------
        * Assert ``profile.full_name`` is non-empty.
        * Assert ``profile.emails`` contains at least one valid address.
        * Assert ``profile.years_experience`` is within a plausible range
          (e.g. 0–60).
        * Warn if ``profile.skills`` is empty.
        * Warn if no ``experience`` entries are present.
        * Assert all ``experience`` date ranges are non-overlapping (optional).
        * Assert confidence scores on critical fields exceed a minimum threshold.
        """
        # TODO: Implement semantic validation rules.
        raise NotImplementedError("ValidationEngine.validate() is not yet implemented.")

    def _check_contact_info(self, profile: CandidateProfile) -> list[str]:
        """
        Validate that the profile contains sufficient contact information.

        TODO (Phase 5): At minimum one email or phone must be present.
        """
        # TODO: Implement contact-info validation rule.
        raise NotImplementedError

    def _check_experience_dates(self, profile: CandidateProfile) -> list[str]:
        """
        Validate that experience date ranges are consistent and non-future.

        TODO (Phase 5): Implement date-range sanity checks.
        """
        # TODO: Implement experience date validation.
        raise NotImplementedError
