"""
Abstract base class for all source adapters.

Every data source (ATS system, resume PDF, LinkedIn export, etc.) must provide
a concrete implementation of :class:`SourceAdapter`.  The adapter's sole
responsibility is to read its source data and return a
:class:`~src.models.CandidateProfile` in the canonical schema.

This contract ensures that the rest of the pipeline (normaliser, merge engine,
projector) is completely decoupled from source-specific formats.

Design notes
------------
* Adapters must be **stateless** after construction — all state needed for
  parsing should be passed to ``__init__``.
* Adapters must **not** perform normalisation — that is the normaliser's job.
* Adapters must **not** raise unhandled exceptions — wrap source errors in
  :class:`AdapterError`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from src.models import CandidateProfile


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class AdapterError(Exception):
    """
    Raised when a source adapter fails to parse or load its input.

    Attributes
    ----------
    source:
        The name of the adapter / source that raised the error.
    cause:
        The original underlying exception, if any.
    """

    def __init__(
        self,
        message: str,
        source: Optional[str] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.source = source
        self.cause = cause

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"AdapterError(source={self.source!r}, message={str(self)!r},"
            f" cause={self.cause!r})"
        )


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class SourceAdapter(ABC):
    """
    Abstract base class that every source adapter must implement.

    A ``SourceAdapter`` acts as an *anti-corruption layer* between a raw,
    source-specific data format and the canonical :class:`CandidateProfile`
    schema.

    Lifecycle
    ---------
    1. Instantiate with source-specific parameters (e.g. file path, API key).
    2. Call :meth:`validate_source` to assert the source is readable.
    3. Call :meth:`parse` to obtain the canonical profile.

    Subclasses must implement
    -------------------------
    * :meth:`parse`
    * :meth:`validate_source`

    Example
    -------
    ::

        adapter = ATSAdapter(path=Path("inputs/candidate.json"))
        adapter.validate_source()
        profile: CandidateProfile = adapter.parse()
    """

    #: Human-readable name for this adapter, used in logging and provenance.
    source_name: str = "unknown"

    @abstractmethod
    def parse(self) -> CandidateProfile:
        """
        Parse the source data and return a canonical ``CandidateProfile``.

        Returns
        -------
        CandidateProfile
            A partially-populated canonical profile.  Fields for which the
            source has no data should be left as ``None`` / empty list.

        Raises
        ------
        AdapterError
            If the source cannot be read or fails structural validation.
        """
        ...

    @abstractmethod
    def validate_source(self) -> None:
        """
        Assert that the source data is accessible and structurally valid.

        This method should perform lightweight checks (file exists, JSON is
        valid, required top-level keys are present) **without** parsing the
        full document.

        Raises
        ------
        AdapterError
            If the source is missing, unreadable, or structurally invalid.
        """
        ...
