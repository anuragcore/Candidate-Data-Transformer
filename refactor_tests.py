import os
import glob
import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    orig = content
    
    # CandidateProfile / Location
    content = content.replace("state=", "region=")
    content = content.replace(".state ", ".region ")
    content = content.replace(".state\n", ".region\n")
    content = content.replace(".state=", ".region=")
    content = content.replace(".state,", ".region,")
    
    # Skill
    content = content.replace('source="ats"', 'sources=["ats"]')
    content = content.replace('source="resume"', 'sources=["resume"]')
    content = content.replace('source="merged"', 'sources=["merged"]')
    content = content.replace('source="test"', 'sources=["test"]')
    content = content.replace('.source ==', '.sources ==')
    content = content.replace('.source ', '.sources ')
    
    # Experience
    content = content.replace("start_date=", "start=")
    content = content.replace("description=", "summary=")
    content = content.replace(".start_date", ".start")
    content = content.replace(".description", ".summary")
    
    # Education
    content = content.replace("field_of_study=", "field=")
    content = content.replace(".field_of_study", ".field")
    # For Education end_date is now end_year
    content = re.sub(r'def _edu\(.*?\):', lambda m: m.group(0).replace('end_date: Optional[date] = None', 'end_year: Optional[str] = None'), content)
    content = re.sub(r'end_date=([^,]+),', r'end_year=\1,', content)
    content = content.replace(".end_date", ".end") # experience uses end
    
    # Provenance
    content = content.replace("field_path=", "field=")
    content = content.replace(".field_path", ".field")
    content = content.replace("notes=", "method=")
    content = content.replace(".notes", ".method")
    
    # Dates
    content = content.replace("date(2020, 1, 1)", '"2020-01"')
    content = content.replace("date(2021, 1, 1)", '"2021-01"')
    content = content.replace("date(2014, 1, 1)", '"2014-01"')
    content = content.replace("date(2018, 5, 1)", '"2018-05"')
    content = content.replace("date(2021, 5, 31)", '"2021-05"')
    content = content.replace("date(2021, 6, 1)", '"2021-06"')
    content = content.replace("date(2019, 1, 1)", '"2019-01"')
    content = content.replace("date(2022, 1, 1)", '"2022-01"')
    
    if orig != content:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Updated {filepath}")

for f in glob.glob("tests/**/*.py", recursive=True):
    process_file(f)
