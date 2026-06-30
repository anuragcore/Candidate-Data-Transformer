import json
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))

def write_pdf(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    _, page_height = A4
    y = page_height - 60
    for line in text.splitlines():
        if y < 60:
            c.showPage()
            y = page_height - 60
        c.setFont("Helvetica", 10)
        c.drawString(60, y, line)
        y -= 14
    c.save()

# Candidate 1: Clean (Everything matches)
write_json(Path("samples/candidate1/ats.json"), {
    "candidateName": "Alice Wonderland",
    "primaryEmail": "alice@gmail.com",
    "mobile": "+91 9876543210",
    "location": "Bangalore",
    "skills": ["Python", "React", "Docker"]
})
write_pdf(Path("samples/candidate1/resume.pdf"), """Alice Wonderland
alice@gmail.com | +91 9876543210
Bangalore

SUMMARY
Software Engineer with expertise in Python, React, and Docker.

SKILLS
Python, React, Docker

EXPERIENCE
Software Engineer at Acme Corp
Jan 2021 - Present
""")

# Candidate 2: Conflict
write_json(Path("samples/candidate2/ats.json"), {
    "candidateName": "John Doe",
    "primaryEmail": "john@example.com",
    "skills": ["Python", "Java"],
    "experience": [
        {
            "title": "Software Engineer",
            "company": "TechCorp",
            "startDate": "2020",
            "endDate": "2022"
        }
    ]
})
write_pdf(Path("samples/candidate2/resume.pdf"), """John Doe
john@example.com

SUMMARY
Senior Backend Engineer.

SKILLS
Python, Java, AWS

EXPERIENCE
Senior Software Engineer at TechCorp
Jan 2020 - Dec 2022
Built cloud services.
""")

# Candidate 3: Missing Data / Invalid formats
write_json(Path("samples/candidate3/ats.json"), {
    "candidateName": "Bob Smith",
    "primaryEmail": "invalid-email-format",
    "mobile": "invalid-phone"
})
write_pdf(Path("samples/candidate3/resume.pdf"), """Bob Smith
(No email provided)
Phone: 12345

SKILLS
Ruby, Rails
""")

print("Sample data generated.")
