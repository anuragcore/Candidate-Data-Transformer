import json
import tempfile
from pathlib import Path
from typing import Any

import streamlit as st

from src.adapters.ats_adapter import ATSAdapter
from src.adapters.resume_adapter import ResumeAdapter
from src.normalizers import Normalizer
from src.merger import MergeEngine
from src.merger.confidence_engine import ConfidenceEngine as MergerConfidenceEngine
from src.confidence import ConfidenceEngine as UIConfidenceEngine
from src.projector import ProjectionEngine
from src.models import ProjectionConfig


st.set_page_config(page_title="Candidate Data Transformer", layout="wide")

st.title("Multi-Source Candidate Data Transformer")

# Pipeline Summary Card
st.markdown("""
<style>
    .pipeline-container {
        display: flex; justify-content: center; align-items: center; gap: 0.8rem; 
        padding: 1.5rem; background: #1E1E1E; border-radius: 12px; margin-bottom: 2rem; 
        border: 1px solid #333; flex-wrap: wrap; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .pipe-node {
        padding: 8px 16px; border-radius: 20px; font-weight: 600; font-size: 0.85rem; letter-spacing: 0.5px;
    }
    .pipe-arrow { color: #666; font-size: 1.2rem; font-weight: bold; }
</style>
<div class="pipeline-container">
    <div class="pipe-node" style="background: #2b5c8f; color: white;">ATS + Resume</div>
    <div class="pipe-arrow">&#10142;</div>
    <div class="pipe-node" style="background: #207a5d; color: white;">Adapters</div>
    <div class="pipe-arrow">&#10142;</div>
    <div class="pipe-node" style="background: #13819e; color: white;">Canonical Profile</div>
    <div class="pipe-arrow">&#10142;</div>
    <div class="pipe-node" style="background: #a36b14; color: white;">Normalization</div>
    <div class="pipe-arrow">&#10142;</div>
    <div class="pipe-node" style="background: #8b2b2b; color: white;">Merge & Conflict Resolution</div>
    <div class="pipe-arrow">&#10142;</div>
    <div class="pipe-node" style="background: #5d2b8b; color: white;">Provenance & Confidence</div>
    <div class="pipe-arrow">&#10142;</div>
    <div class="pipe-node" style="background: #a39514; color: white;">Projection</div>
    <div class="pipe-arrow">&#10142;</div>
    <div class="pipe-node" style="background: #b35a1f; color: white;">Validation</div>
    <div class="pipe-arrow">&#10142;</div>
    <div class="pipe-node" style="background: #2b8f3a; color: white;">Final Output</div>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
with col1:
    ats_file = st.file_uploader("Upload ATS JSON", type=["json"])
with col2:
    resume_file = st.file_uploader("Upload Resume PDF", type=["pdf"])
with col3:
    config_file = st.file_uploader("Upload Projection Config (Optional)", type=["json"])

def format_display_value(val: Any) -> str:
    """Formatter to clean up internal object representation for UI tables."""
    if isinstance(val, list):
        if len(val) > 0 and hasattr(val[0], 'name'):
            return ", ".join(v.name for v in val)
        return ", ".join(str(v) for v in val)
    if hasattr(val, 'name'):
        return val.name
    if hasattr(val, 'city'):
        parts = []
        if getattr(val, 'city', None): parts.append(val.city)
        if getattr(val, 'country', None): parts.append(val.country)
        if parts:
            return ", ".join(parts)
        return getattr(val, 'raw', '') or str(val)
    return str(val)

def cleanup_json_for_ui(data: Any) -> Any:
    """Recursively cleans up dictionaries to replace internal structures with flat strings for UI JSON."""
    if isinstance(data, dict):
        if set(data.keys()).issuperset({"city", "region", "country", "raw"}):
            parts = []
            if data.get("city"): parts.append(data["city"])
            if data.get("country"): parts.append(data["country"])
            if parts: return ", ".join(parts)
            return data.get("raw") or ""
        if set(data.keys()).issuperset({"name", "confidence", "sources", "level"}):
            return data["name"]
        return {k: cleanup_json_for_ui(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [cleanup_json_for_ui(v) for v in data]
    return data

def process_pipeline():
    if not ats_file and not resume_file:
        st.error("Please upload at least one file (ATS JSON or Resume PDF) to proceed.")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        config_path = Path("config/default_projection.json")
        if config_file:
            config_path = tmp_path / "config.json"
            config_path.write_bytes(config_file.getvalue())
            
        try:
            # Display Config
            config_dict = json.loads(config_path.read_text(encoding="utf-8"))
            if "name" not in config_dict:
                config_dict["name"] = "custom_projection"
            with st.expander("Active Projection Config", expanded=False):
                st.json(config_dict)
                
            # Extract
            from src.models import CandidateProfile
            ats_profile = CandidateProfile()
            resume_profile = CandidateProfile()
            
            if ats_file:
                ats_path = tmp_path / "ats.json"
                ats_path.write_bytes(ats_file.getvalue())
                ats_adapter = ATSAdapter(ats_path)
                ats_profile = ats_adapter.parse()
                
            if resume_file:
                resume_path = tmp_path / "resume.pdf"
                resume_path.write_bytes(resume_file.getvalue())
                resume_adapter = ResumeAdapter(resume_path)
                resume_profile = resume_adapter.parse()
            
            # Normalize
            normalizer = Normalizer()
            ats_norm = normalizer.normalize(ats_profile)
            resume_norm = normalizer.normalize(resume_profile)
            
            # Merge
            merger = MergeEngine()
            merge_result = merger.merge(ats_norm, resume_norm)
            canonical = merge_result.merged_profile
            
            # Confidence
            conf_engine = MergerConfidenceEngine()
            canonical = conf_engine.calculate_confidence(merge_result)
            
            # Project
            proj_config = ProjectionConfig(**config_dict)
            projector = ProjectionEngine(proj_config)
            projected = projector.project(canonical)
            
            # Stats Summary
            st.success("Pipeline executed successfully!")
            sc1, sc2, sc3, sc4, sc5 = st.columns(5)
            sc1.metric("Emails Found", len(canonical.emails))
            sc2.metric("Phones Found", len(canonical.phones))
            sc3.metric("Skills Found", len(canonical.skills))
            sc4.metric("Merge Decisions", len(merge_result.merge_decisions))
            
            # Overall Confidence Calculation
            engine = UIConfidenceEngine()
            conf_results = engine.compute(canonical)
            if conf_results:
                overall = sum(r.confidence for r in conf_results) / len(conf_results)
            else:
                overall = 1.0
            sc5.metric("Overall Confidence", f"{overall:.2f}")
            
            # Result Tabs
            t1, t2, t3, t4, t5 = st.tabs([
                "Canonical Profile", 
                "Projected Output", 
                "Merge Decisions", 
                "Confidence Scores", 
                "Provenance"
            ])
            
            with t1:
                canonical_clean = cleanup_json_for_ui(canonical.model_dump(mode="json"))
                canonical_json = json.dumps(canonical_clean, indent=2)
                st.download_button(
                    label="Download Canonical JSON",
                    data=canonical_json,
                    file_name="canonical_profile.json",
                    mime="application/json"
                )
                st.json(canonical_json)
                
            with t2:
                from pydantic import TypeAdapter
                projected_raw = TypeAdapter(dict).dump_python(projected, mode="json")
                projected_clean = cleanup_json_for_ui(projected_raw)
                projected_json = json.dumps(projected_clean, indent=2)
                st.download_button(
                    label="Download Projected JSON",
                    data=projected_json,
                    file_name="projected_output.json",
                    mime="application/json"
                )
                st.json(projected_json)
                
            with t3:
                decisions = []
                for d in merge_result.merge_decisions:
                    row = d.model_dump(mode="json")
                    row["chosen_value"] = format_display_value(d.chosen_value)
                    if d.discarded_value is not None:
                        row["discarded_value"] = format_display_value(d.discarded_value)
                    decisions.append(row)
                st.dataframe(decisions, use_container_width=True)
                
            with t4:
                engine = UIConfidenceEngine()
                conf_results = engine.compute(canonical)
                conf_data = [{"Field": r.field_name, "Value": format_display_value(r.value), "Confidence": r.confidence, "Sources": ", ".join(r.sources), "Reason": r.reason} for r in conf_results]
                st.dataframe(conf_data, use_container_width=True)
                
            with t5:
                provs = [p.model_dump(mode="json") for p in canonical.provenance]
                st.dataframe(provs, use_container_width=True)
                
        except Exception as e:
            st.error(f"Pipeline Execution Failed: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

if st.button("Transform Candidate", type="primary"):
    process_pipeline()
