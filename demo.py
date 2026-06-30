"""
demo.py — End-to-end Phase 2 demonstration.

Runs both ATSAdapter and ResumeAdapter on real sample inputs and prints
a detailed extraction report to the terminal.  Outputs are also written
as JSON files to the output/ directory.

Usage
-----
    PYTHONPATH=. python demo.py

No arguments required — all inputs are generated/located automatically.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Colour helpers (no external deps — plain ANSI codes)
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"
DIM    = "\033[2m"

def h1(text: str) -> None:
    width = 70
    print(f"\n{BOLD}{CYAN}{'━' * width}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'━' * width}{RESET}")

def h2(text: str) -> None:
    print(f"\n{BOLD}{YELLOW}  ▶  {text}{RESET}")

def ok(text: str) -> None:
    print(f"  {GREEN}✔{RESET}  {text}")

def info(label: str, value: str) -> None:
    print(f"    {DIM}{label:<22}{RESET}{value}")

def warn(text: str) -> None:
    print(f"  {YELLOW}⚠{RESET}  {text}")

def err(text: str) -> None:
    print(f"  {RED}✘{RESET}  {text}")

def section_divider() -> None:
    print(f"\n  {DIM}{'─' * 60}{RESET}")


# ---------------------------------------------------------------------------
# Step 1 — ensure sample inputs exist
# ---------------------------------------------------------------------------

def ensure_sample_ats() -> Path:
    """Return path to the sample ATS JSON (already in tests/fixtures/)."""
    p = Path("tests/fixtures/sample_ats.json")
    if not p.exists():
        err(f"ATS fixture not found: {p}  (run tests first to generate fixtures)")
        sys.exit(1)
    return p


def ensure_sample_resume() -> Path:
    """
    Generate a sample résumé PDF if it doesn't already exist.
    Uses reportlab — same approach as the test conftest.
    """
    pdf_path = Path("tests/fixtures/sample_resume.pdf")
    if pdf_path.exists():
        return pdf_path

    print(f"  {DIM}Generating sample_resume.pdf ...{RESET}")
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        err("reportlab not installed. Run: pip install reportlab")
        sys.exit(1)

    resume_text = """\
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
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    _, page_height = A4
    y = page_height - 60
    for line in resume_text.splitlines():
        if y < 60:
            c.showPage()
            y = page_height - 60
        c.setFont("Helvetica", 10)
        c.drawString(60, y, line)
        y -= 14
    c.save()
    return pdf_path


# ---------------------------------------------------------------------------
# Step 2 — run adapters
# ---------------------------------------------------------------------------

def run_ats_adapter(ats_path: Path):
    from src.adapters import ATSAdapter
    from src.adapters.base import AdapterError

    h1("ATS ADAPTER")
    print(f"  {DIM}Input: {ats_path}{RESET}\n")

    try:
        adapter = ATSAdapter(path=ats_path)
        adapter.validate_source()
        ok("validate_source() passed")
        profile = adapter.parse()
        ok("parse() succeeded")
    except AdapterError as exc:
        err(f"AdapterError: {exc}")
        return None

    _print_profile(profile, source="ATS")
    return profile


def run_resume_adapter(pdf_path: Path):
    from src.adapters import ResumeAdapter
    from src.adapters.base import AdapterError

    h1("RESUME ADAPTER (PDF)")
    print(f"  {DIM}Input: {pdf_path}{RESET}\n")

    try:
        adapter = ResumeAdapter(path=pdf_path)
        adapter.validate_source()
        ok("validate_source() passed")
        profile = adapter.parse()
        ok("parse() succeeded")
    except AdapterError as exc:
        err(f"AdapterError: {exc}")
        return None

    _print_profile(profile, source="Resume PDF")
    return profile


# ---------------------------------------------------------------------------
# Step 3 — print profile details
# ---------------------------------------------------------------------------

def _print_profile(profile, source: str) -> None:
    h2(f"Extracted CandidateProfile  [{source}]")

    section_divider()
    print(f"  {BOLD}Contact{RESET}")
    info("full_name",       profile.full_name or "(not found)")
    info("emails",          ", ".join(profile.emails) if profile.emails else "(none)")
    info("phones",          ", ".join(profile.phones) if profile.phones else "(none)")
    info("location",        profile.location.raw if profile.location else "(none)")
    info("headline",        profile.headline or "(none)")
    info("years_experience",str(profile.years_experience) if profile.years_experience else "(none)")

    section_divider()
    print(f"  {BOLD}Links{RESET}")
    if profile.links:
        for lk in profile.links:
            ok(str(lk))
    else:
        warn("No links extracted")

    section_divider()
    print(f"  {BOLD}Skills  ({len(profile.skills)} found){RESET}")
    if profile.skills:
        names = [s.name for s in profile.skills]
        # Print in rows of 5
        for i in range(0, len(names), 5):
            print("    " + "  ·  ".join(f"{GREEN}{n}{RESET}" for n in names[i:i+5]))
    else:
        warn("No skills extracted")

    section_divider()
    print(f"  {BOLD}Experience  ({len(profile.experience)} entries){RESET}")
    for exp in profile.experience:
        current = f" {GREEN}[current]{RESET}" if exp.is_current else ""
        print(f"    {BOLD}{exp.title or '?'}{RESET}  @  {exp.company or '?'}{current}")
        date_str = f"{exp.start_date} → {'Present' if exp.is_current else exp.end_date}"
        print(f"      {DIM}{date_str}{RESET}")
        if exp.description:
            wrapped = textwrap.shorten(exp.description, width=60, placeholder="…")
            print(f"      {DIM}{wrapped}{RESET}")

    section_divider()
    print(f"  {BOLD}Education  ({len(profile.education)} entries){RESET}")
    for edu in profile.education:
        print(f"    {BOLD}{edu.institution or '?'}{RESET}")
        print(f"      {edu.degree.value}  ·  {edu.field_of_study or '?'}")
        date_str = f"{edu.start_date} → {edu.end_date}"
        print(f"      {DIM}{date_str}{RESET}")

    section_divider()
    print(f"  {BOLD}Provenance  ({len(profile.provenance)} records){RESET}")
    methods: dict[str, int] = {}
    for rec in profile.provenance:
        method = (rec.notes or "unknown").replace("method=", "")
        methods[method] = methods.get(method, 0) + 1
    for method, count in sorted(methods.items()):
        info(method, f"{count} field(s)")


# ---------------------------------------------------------------------------
# Step 4 — write JSON output
# ---------------------------------------------------------------------------

def write_output(profile, name: str) -> None:
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{name}.json"

    data = profile.model_dump(mode="json")
    out_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    ok(f"Output written → {out_path}")


# ---------------------------------------------------------------------------
# Step 5 — error handling demo (malformed JSON)
# ---------------------------------------------------------------------------

def demo_error_handling() -> None:
    from src.adapters import ATSAdapter
    from src.adapters.base import AdapterError

    h1("ERROR HANDLING DEMO")
    malformed = Path("tests/fixtures/malformed_ats.json")
    print(f"  {DIM}Feeding malformed JSON: {malformed}{RESET}\n")

    try:
        ATSAdapter(path=malformed).parse()
        warn("No error raised — unexpected!")
    except AdapterError as exc:
        ok(f"AdapterError correctly raised: {BOLD}{exc}{RESET}")

    missing = Path("inputs/does_not_exist.json")
    print()
    try:
        ATSAdapter(path=missing).validate_source()
        warn("No error raised — unexpected!")
    except AdapterError as exc:
        ok(f"AdapterError for missing file: {BOLD}{exc}{RESET}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"\n{BOLD}{CYAN}Multi-Source Candidate Data Transformer — Phase 2 Demo{RESET}")
    print(f"{DIM}Python path: {sys.executable}{RESET}")

    ats_path    = ensure_sample_ats()
    resume_path = ensure_sample_resume()

    ats_profile    = run_ats_adapter(ats_path)
    resume_profile = run_resume_adapter(resume_path)

    h1("OUTPUT")
    if ats_profile:
        write_output(ats_profile, "ats_profile")
    if resume_profile:
        write_output(resume_profile, "resume_profile")

    demo_error_handling()

    h1("DONE")
    ok("Both adapters ran successfully.")
    ok("Check output/ats_profile.json and output/resume_profile.json")
    print()


if __name__ == "__main__":
    main()
