# Multi-Source Candidate Data Transformer

> **Live Demo:** [https://candidate-data-transformer.streamlit.app/](https://candidate-data-transformer.streamlit.app/)

The Multi-Source Candidate Data Transformer ingests candidate data from heterogeneous sources (structured ATS JSON + unstructured résumé PDFs), normalizes it, and fuses it into a single, authoritative Canonical Candidate Profile.

## Architecture

ATS JSON + Resume PDF ➔ Adapters ➔ Canonical Profile ➔ Normalization ➔ Merge & Conflict Resolution ➔ Provenance & Confidence ➔ Projection ➔ Validation ➔ Final Output

## Quick Start (CLI / Streamlit)

**Prerequisites:** Python 3.11+

```bash
git clone https://github.com/anuragcore/Candidate-Data-Transformer.git
cd Candidate-Data-Transformer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Run the UI (Recommended):**
```bash
streamlit run app.py
```

## Running Tests
The project contains 208 tests with 100% core coverage.
```bash
pytest tests/ -v
```

## Sample Inputs
Use the provided `samples/` directory to evaluate the system's behavior:
- **Candidate A (`candidate_a.json`)**: Baseline agreement scenario. Expect high confidence scores (1.00) due to source corroboration.
- **Candidate B (`candidate_b.json`)**: Source conflict scenario. The engine applies deterministic conflict resolution and accurately downgrades confidence (0.70).
- **Candidate C (`candidate_c.json`)**: Malformed/missing data scenario. The pipeline gracefully degrades without crashing.

## Assumptions & Limitations
- **Assumptions**: ATS JSON files follow a semi-structured key-value format. Résumé PDFs have parseable text layers (not scanned images).
- **Limitations**: The current deterministic parser does not extract highly nested, unstructured multi-page project arrays perfectly without an ML/NLP layer. We explicitly chose to omit fuzzy guessing in favor of strict "wrong-but-confident is worse than honestly-empty" constraints.
