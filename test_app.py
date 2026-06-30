import sys
import json
from pathlib import Path
from src.adapters.ats_adapter import ATSAdapter
from src.adapters.resume_adapter import ResumeAdapter
from src.normalizers import Normalizer
from src.merger import MergeEngine
from src.merger.confidence_engine import ConfidenceEngine
from src.projector import ProjectionEngine
from src.models import ProjectionConfig

def test_pipeline():
    ats_path = Path("tests/fixtures/sample_ats.json")
    resume_path = Path("tests/fixtures/sample_resume.pdf")
    config_path = Path("config/default_projection.json")

    ats_adapter = ATSAdapter(ats_path)
    ats_profile = ats_adapter.parse()

    resume_adapter = ResumeAdapter(resume_path)
    resume_profile = resume_adapter.parse()

    normalizer = Normalizer()
    ats_norm = normalizer.normalize(ats_profile)
    resume_norm = normalizer.normalize(resume_profile)

    merger = MergeEngine()
    merge_result = merger.merge(ats_norm, resume_norm)
    
    conf_engine = ConfidenceEngine()
    canonical = conf_engine.calculate_confidence(merge_result)

    config_dict = json.loads(config_path.read_text(encoding="utf-8"))
    proj_config = ProjectionConfig(**config_dict)
    projector = ProjectionEngine(proj_config)
    projected = projector.project(canonical)

    print("Success! Emails found:", len(canonical.emails))
    print("Overall confidence:", canonical.overall_confidence)

if __name__ == "__main__":
    test_pipeline()
