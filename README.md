# Multi-Source Candidate Data Transformer

> **Python 3.11+ · Pydantic v2 · Clean Architecture · SOLID Principles**

The **Multi-Source Candidate Data Transformer** ingests candidate data from heterogeneous sources — a structured ATS JSON export and an unstructured résumé PDF — and fuses them into a single, authoritative **Canonical Candidate Profile**.

---

## Architecture Diagram

```
ATS JSON
        \
         -> Extract
Resume PDF /
             ↓
        Normalize
             ↓
          Merge
             ↓
       Confidence
             ↓
        Projection
             ↓
          Output
```

## Pipeline Flow

The pipeline executes through a sequence of strict, deterministic stages:

1. **Extract**: Data is extracted independently from the ATS JSON (via `ATSAdapter`) and the Resume PDF (via `ResumeAdapter`). The resume extraction uses lightweight regex and section heuristics rather than NLP or ML models.
2. **Normalize**: Both profiles pass through the `Normalizer` where scalars and collections are standardized (e.g., lowercase emails, E.164 phone formats, date standardization to `YYYY-MM`).
3. **Merge**: The `MergeEngine` takes both normalized profiles and systematically resolves conflicts and deduplicates lists to form a single canonical profile.
4. **Compute Confidence**: The `ConfidenceEngine` evaluates the source of each field and applies deterministic confidence scores based on source reliability and cross-source agreement.
5. **Project Output**: The `ProjectionEngine` formats the canonical profile based on a runtime JSON configuration, producing the final output shape without altering internal logic.

---

## Canonical Schema

The **Canonical Candidate Profile** acts as the single source of truth and data contract for the entire system.

By mapping all sources into one `CandidateProfile`, the pipeline achieves:
- **Consistency**: All downstream processors interact with one predictable schema regardless of input variance.
- **Source Independence**: The core engine doesn't care whether data came from a PDF, an ATS, or an API.
- **Simpler Merging**: Conflict resolution is centralized rather than duplicated across adapters.
- **Configurable Projection**: The final output can be re-shaped dynamically without rewriting the core object models.

---

## Merge Strategy

The `MergeEngine` combines two canonical profiles using distinct strategies based on field types:
- **Scalars** (e.g., name, headline, location): Resolved via priority-based rules (ATS is generally prioritized, but Resume wins for specific fields like display name and headline).
- **Collections** (e.g., skills, emails, experience): Resolved via union followed by composite-key deduplication.

## Conflict Resolution

When scalar values conflict, the engine records an immutable `MergeDecision` detailing exactly why a choice was made.

**Example Conflict:**
- **Resume**: Anurag
- **ATS**: Anurag Ojha
- **Winner**: Resume
- **Reason**: `resume_priority` (The resume name is typically what the candidate explicitly prefers).

---

## Confidence Strategy

The deterministic `ConfidenceEngine` assigns scores to extracted fields based **only** on source reliability and source corroboration. It deliberately avoids statistical probability scoring, ML, or taxonomy quality measures.

- **ATS only -> 0.90**: High trust, treated as structured ground truth.
- **Resume only -> 0.80**: Moderate trust due to the unstructured nature of PDFs.
- **Agreement -> 1.00**: When ATS and Resume provide the exact same data, confidence is boosted.
- **Conflict -> 0.70**: When sources provide data for the same field but disagree.
- **Unknown -> 0.50**: Fallback for fields lacking provenance.

Confidence represents source reliability + source corroboration, not statistical certainty.

---

## Projection Layer

The `ProjectionEngine` translates the dense, complete canonical schema into a target output format. This layer uses runtime configuration files (e.g., `config/default_projection.json`) to control field selection, renaming, and nesting. This allows the system to change its output schema instantly for different consumers without modifying the underlying Python models or logic.

---

## Design Trade-Offs

**Why was deterministic extraction chosen over LLMs/ML?**

- **Predictable**: Regex and keyword heuristics always produce the same output for the same input.
- **Auditable**: Every field can be traced back to the exact line of code that extracted it (provenance).
- **Repeatable**: No stochastic variance between pipeline runs.
- **No Hallucinations**: The system will never invent data; it will return `null` instead of guessing.
- **Low Cost**: Runs entirely on CPU with zero API calls or GPU requirements.
- **Easy to Defend**: In recruiting, explainability is legally and ethically paramount. Rule-based systems provide a clear paper trail for every decision.

---

## Getting Started

### Prerequisites
- Python 3.11+
- Virtual environment

### Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Verification Plan

You can verify the system through automated tests or the interactive Streamlit UI.

#### Automated Testing
Run the test suite to ensure all baseline parsers and engines pass:
```bash
pytest tests/ -v
```

#### Manual Testing (Streamlit)
```bash
streamlit run app.py
```

Use the provided `samples/` directory to test the edge cases:
- **Candidate A (`candidate_a.json`)**: An agreement scenario. Expect confidence scores to hit `1.00` for matching fields.
- **Candidate B (`candidate_b.json`)**: A conflict scenario. Watch the system create detailed `MergeDecision` records and apply conflict confidence scores (`0.70`).
- **Candidate C (`candidate_c.json`)**: A bad data scenario. The pipeline handles missing emails and malformed phones gracefully without crashing.
