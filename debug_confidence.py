import json
from pathlib import Path
from src.adapters.ats_adapter import ATSAdapter
from src.adapters.resume_adapter import ResumeAdapter
from src.normalizers import Normalizer
from src.merger import MergeEngine
from src.merger.confidence_engine import ConfidenceEngine

ats_path = Path("samples/candidate_a.json")
resume_path = Path("tests/fixtures/sample_resume.pdf")

ats_profile = ATSAdapter(ats_path).parse()
resume_profile = ResumeAdapter(resume_path).parse()

normalizer = Normalizer()
ats_norm = normalizer.normalize(ats_profile)
resume_norm = normalizer.normalize(resume_profile)

merger = MergeEngine()
merge_result = merger.merge(ats_norm, resume_norm)

conf_engine = ConfidenceEngine()
canonical = conf_engine.calculate_confidence(merge_result)

for prov in canonical.provenance:
    print(f"Field: {prov.field}, Source: {prov.source}, Raw: {prov.raw_value}, Confidence: {prov.confidence}")
