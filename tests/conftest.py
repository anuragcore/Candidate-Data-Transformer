"""
conftest.py — pytest fixtures for Phase 2 tests.

All binary artefacts (PDFs) are generated programmatically here using
``reportlab`` so that no binary blobs are committed to the repository.

Fixture scope
-------------
* ``sample_resume_pdf`` — session-scoped: generated once, reused by all tests.
* ``tmp_pdf_factory`` — function-scoped factory for custom PDF content.
* All JSON fixtures are read directly from ``tests/fixtures/`` as files.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)

SAMPLE_RESUME_PATH = FIXTURES_DIR / "sample_resume.pdf"


# ---------------------------------------------------------------------------
# PDF generation helpers
# ---------------------------------------------------------------------------

def _make_resume_pdf(path: Path, text: str) -> Path:
    """
    Write ``text`` into a one-page PDF at ``path`` using reportlab.

    Parameters
    ----------
    path:
        Destination path (parent must exist).
    text:
        Multi-line string to render in the PDF.

    Returns
    -------
    Path
        The path to the generated PDF.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    page_width, page_height = A4
    x_margin = 60
    y = page_height - 60
    line_height = 14

    for line in text.splitlines():
        if y < 60:
            c.showPage()
            y = page_height - 60
        c.setFont("Helvetica", 10)
        c.drawString(x_margin, y, line)
        y -= line_height

    c.save()
    return path


# ---------------------------------------------------------------------------
# Canonical résumé text (realistic, exercises all extractors)
# ---------------------------------------------------------------------------

SAMPLE_RESUME_TEXT = """\
Alice Wonderland
alice.wonderland@example.com | +1 (415) 555-0199
https://linkedin.com/in/alicewonderland | https://github.com/alicewonder
Bangalore, India

SUMMARY
Experienced Software Engineer with 5 years of expertise in Python and React.

SKILLS
Python, JavaScript, TypeScript, React, Node.js, PostgreSQL, Docker, AWS, Git

EXPERIENCE
Senior Software Engineer at TechCorp
Jan 2021 - Present
Built scalable microservices using Python and FastAPI.
Reduced API latency by 40% through caching with Redis.

Software Engineer at WebStartup
Jun 2018 - Dec 2020
Developed React frontend and Django REST backend.
Managed PostgreSQL databases and Docker deployments.

EDUCATION
Bachelor of Technology in Computer Science
Indian Institute of Technology Bombay
2014 - 2018
"""

RESUME_NO_EMAIL_TEXT = """\
Bob Builder
+44 7911 123456
https://linkedin.com/in/bobbuilder

SKILLS
Java, Spring, Docker, Kubernetes, AWS

EXPERIENCE
Java Developer at BuildCo
Mar 2019 - Present
Developed microservices using Spring Boot.

EDUCATION
Master of Science in Software Engineering
University of Manchester
2016 - 2018
"""

RESUME_NO_PHONE_TEXT = """\
Carol Danvers
carol@hero.com
https://github.com/caroldanvers

SKILLS
Python, Machine Learning, TensorFlow, PyTorch

EXPERIENCE
ML Engineer at HeroTech
Jan 2020 - Present
Trained deep learning models for NLP tasks.

EDUCATION
PhD in Computer Science
MIT
2014 - 2019
"""


# ---------------------------------------------------------------------------
# Session-scoped fixtures (generated once per test session)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_resume_pdf() -> Path:
    """
    Generate a realistic résumé PDF and return its path.

    Generated once per test session.  The file lives in
    ``tests/fixtures/sample_resume.pdf``.
    """
    return _make_resume_pdf(SAMPLE_RESUME_PATH, SAMPLE_RESUME_TEXT)


@pytest.fixture(scope="session")
def resume_no_email_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """PDF résumé with phone and LinkedIn but NO email address."""
    path = tmp_path_factory.mktemp("pdfs") / "no_email_resume.pdf"
    return _make_resume_pdf(path, RESUME_NO_EMAIL_TEXT)


@pytest.fixture(scope="session")
def resume_no_phone_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """PDF résumé with email and GitHub but NO phone number."""
    path = tmp_path_factory.mktemp("pdfs") / "no_phone_resume.pdf"
    return _make_resume_pdf(path, RESUME_NO_PHONE_TEXT)


# ---------------------------------------------------------------------------
# Function-scoped factory fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_pdf_factory(tmp_path: Path) -> Callable[[str], Path]:
    """
    Return a factory function that creates a temporary PDF from ``text``.

    Usage::

        def test_something(tmp_pdf_factory):
            pdf_path = tmp_pdf_factory("Custom resume text here")
            adapter = ResumeAdapter(path=pdf_path)
            ...
    """
    counter = [0]

    def _factory(text: str) -> Path:
        counter[0] += 1
        path = tmp_path / f"resume_{counter[0]}.pdf"
        return _make_resume_pdf(path, text)

    return _factory


# ---------------------------------------------------------------------------
# JSON fixture paths
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_ats_path() -> Path:
    """Path to the well-formed ATS JSON fixture."""
    return FIXTURES_DIR / "sample_ats.json"


@pytest.fixture()
def minimal_ats_path() -> Path:
    """Path to the minimal (name-only) ATS JSON fixture."""
    return FIXTURES_DIR / "minimal_ats.json"


@pytest.fixture()
def malformed_ats_path() -> Path:
    """Path to the intentionally malformed ATS JSON fixture."""
    return FIXTURES_DIR / "malformed_ats.json"
