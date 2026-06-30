# Multi-Source Candidate Data Transformer

**Live Demo:** [https://candidate-data-transformer-n9ahkjmob9b6r3srjm947g.streamlit.app/](https://candidate-data-transformer-n9ahkjmob9b6r3srjm947g.streamlit.app/)<br>
**Demo Video:** [Watch on Google Drive](https://drive.google.com/file/d/1goU8VCE0aH4i6RNYnFc_1TLyZTdMZ2Wa/view?usp=sharing)

## Project Overview
This pipeline ingests candidate data from heterogeneous sources (structured ATS JSON and unstructured résumé PDFs) and fuses them into a single, authoritative Canonical Candidate Profile. It performs deterministic extraction, data normalization, and conflict resolution via a dedicated Merge Engine. Every field is tracked with precise provenance and scored by a Confidence Engine, before being passed to a runtime Projection Engine that enables configurable output shapes without altering internal architecture.

## Architecture

```mermaid
graph TD
    %% Styling Definitions
    classDef source fill:#f9f9f9,stroke:#333,stroke-width:1px,color:#333,font-weight:bold
    classDef adapter fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1,font-weight:bold
    classDef model fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20,font-weight:bold
    classDef processor fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#e65100,font-weight:bold
    classDef output fill:#f3e5f5,stroke:#4a148c,stroke-width:2px,color:#4a148c,font-weight:bold

    %% Inputs
    ATS["ATS JSON<br/><span style='font-weight:normal;font-size:12px'>(Structured Source)</span>"]:::source
    RESUME["Resume PDF<br/><span style='font-weight:normal;font-size:12px'>(Unstructured Source)</span>"]:::source

    %% Adapters
    subgraph S1 [Extraction]
        ADAPT_ATS["ATS Adapter"]:::adapter
        ADAPT_RES["Resume Adapter"]:::adapter
    end

    %% Flow from sources
    ATS --> ADAPT_ATS
    RESUME --> ADAPT_RES

    %% Canonical Model
    CANONICAL["Canonical Candidate Profile<br/><span style='font-weight:normal;font-size:12px'>(Single Source of Truth)</span>"]:::model
    
    ADAPT_ATS --> CANONICAL
    ADAPT_RES --> CANONICAL

    %% Processors
    subgraph S2 [Transformation Pipeline]
        direction TB
        NORM["Normalization Layer<br/><div style='text-align:left;font-weight:normal;font-size:12px;margin-top:4px'>• Emails & Phones (E.164)<br/>• Skills Canonicalization<br/>• Location Normalization</div>"]:::processor
        
        MERGE["Merge Engine<br/><div style='text-align:left;font-weight:normal;font-size:12px;margin-top:4px'>• Conflict Resolution<br/>• Deduplication</div>"]:::processor
        
        CONF["Confidence Engine<br/><div style='text-align:left;font-weight:normal;font-size:12px;margin-top:4px'>• Source Agreement<br/>• Conflict Penalties</div>"]:::processor
        
        PROJ["Projection Layer<br/><div style='text-align:left;font-weight:normal;font-size:12px;margin-top:4px'>• Field Selection / Remapping<br/>• Missing Value Handling<br/>(Runtime Config)</div>"]:::processor
        
        VALID["Schema Validation<br/><div style='text-align:left;font-weight:normal;font-size:12px;margin-top:4px'>• Validate Projected Output</div>"]:::processor
    end

    CANONICAL --> NORM
    NORM --> MERGE
    MERGE --> CONF
    CONF --> PROJ
    PROJ --> VALID

    %% Output
    FINAL["Final Output JSON"]:::output

    VALID --> FINAL
```

## Sample Inputs
The pipeline accepts raw inputs. For complete examples, see the `samples/` directory.

**Example ATS JSON snippet:**
```json
{
  "candidateName": "Anurag",
  "primaryEmail": "anurag612@gmail.com",
  "mobile": "+916206478201"
}
```

## Produced Canonical Output
The system generates a rich canonical representation containing merged data, confidence scores, and provenance.

**Example Output snippet:**
```json
{
  "full_name": "Anurag",
  "emails": ["anurag612@gmail.com"],
  "phones": ["+916206478201"],
  "overall_confidence": 0.84
}
```

## Projection Example
The output can be dynamically reshaped at runtime using a JSON configuration.

**Projection Config:**
```json
{
  "fields": [
    {
      "path": "candidate_name",
      "from": "full_name"
    }
  ]
}
```

**Projected Output:**
```json
{
  "candidate_name": "Anurag"
}
```

## How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# Launch the interactive UI
streamlit run app.py
```

## How to Test

```bash
# Run the complete automated test suite
pytest
```

## Assumptions
- The candidate's name appears near the top of the resume.
- The resume follows common formatting conventions (standard headings for Experience, Education, etc.).
- Skills are mapped through a predefined local taxonomy.
- Missing values are explicitly returned as `null` rather than invented/guessed.

## Known Limitations
- Extraction relies on deterministic heuristics and regex.
- No OCR support for scanned images (requires parseable PDF text).
- No fuzzy entity resolution (relies on exact matches or taxonomy).
- No AI/LLM-based extraction components.
