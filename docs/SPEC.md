# Healthcare Claims Extraction Engine — Project Specification

## 🎯 AI Engineering Hackathon 2026 Submission

**Competition Deadline**: August 2, 2026  
**Submission Date**: July 30, 2026  
**Status**: Production-ready prototype with all deliverables complete

### Quick Navigation for Judges

**⏱️ 15-Minute Quick Review:**
1. [../README.md](../README.md) - Key metrics and overview
2. [innovation_highlights.md](innovation_highlights.md) - 5 key differentiators
3. [cost_analysis.md](cost_analysis.md) - $0.0094/page breakdown

**⏱️ 60-Minute Deep Dive:**
4. [accuracy_analysis.md](accuracy_analysis.md) - 90-95% field-level accuracy
5. [architecture.md](architecture.md) - System design with diagrams
6. [throughput_benchmark.md](throughput_benchmark.md) - Performance analysis
7. This document (SPEC.md) - Complete specification

**⏱️ Technical Verification:**
- Run tests: `pytest tests/ -v` (29 tests, ~30-60s)
- Review code: [`../src/`](../src/) - Modular Python codebase
- Try demo: `streamlit run ../ui/streamlit_app.py`

---

> Use this document as the master spec/prompt when building this project with an AI coding
> assistant (GitHub Copilot, Claude, etc.). It contains the business context, verified dataset
> structure, architecture, tech stack, and a phase-by-phase build plan with acceptance criteria.

---

## 1. Project Goal (one sentence)

Build a claims-document extraction pipeline that reads scanned healthcare claim forms
(CMS-1500 and UB-04) and outputs structured field data, maximizing accuracy while minimizing
cost-per-page, in a way that scales to 100M+ pages/year.

## 2. Business Context

Healthcare mailrooms receive millions of scanned pages/year: standardized claim forms
(CMS-1500, UB-04), separator/cover sheets, and supporting attachments. Traditional OCR is cheap
but error-prone on messy scans; LLMs are accurate but expensive at scale. The goal is a hybrid
system that routes each page/field to the cheapest method that still meets accuracy needs.

### Scoring rubric (evaluated per document tier, then combined)

| Category | Weight | Notes |
|---|---|---|
| Extraction accuracy | 35% | Minimize reliance on human-in-the-loop (HITL) |
| Cost per page | 35% | Assume enterprise scale (millions of pages) |
| Innovation & creativity | 10% | |
| Scalability & performance | 10% | |
| Simplicity & maintainability | 10% | |

### Required deliverables

All 8 hackathon deliverables are complete and available in this repository:

1. ✅ **[Solution Architecture](architecture.md)** - Hybrid OCR+LLM system design with diagrams
2. ✅ **[Technical Design](technical_design.md)** - Data schemas, APIs, field mappings, decision logic
3. ✅ **Working Prototype** - [`../src/`](../src/) + [`../ui/streamlit_app.py`](../ui/streamlit_app.py) + [`../tests/`](../tests/) (29 tests passing)
4. ✅ **[Cost Analysis](cost_analysis.md)** - $0.0094/page with 81% savings vs. all-LLM
5. ✅ **[Accuracy Analysis](accuracy_analysis.md)** - 90-95% field-level accuracy measurements
6. ✅ **[Throughput Benchmark](throughput_benchmark.md)** - 450-900 pages/hour per worker
7. ✅ **[Innovation Highlights](innovation_highlights.md)** - 5 key technical differentiators
8. ✅ **[Future Roadmap](roadmap.md)** - 18-month path to enterprise production

This document (SPEC.md) serves as the master specification and project overview.

---

## 3. Dataset — Verified Structure (from actual sample files)

The sample dataset (`Images___Output.zip`) contains 4 batch folders. **Note: folder names
(Group A/B/C/D) do correspond to the brief's Tier A/B/C/D concepts, but this was verified by
inspection, not assumed.**

| Folder | Images | Claims | Ground truth format | Verified tier behavior |
|---|---|---|---|---|
| Group A | 12 TIFFs | 12 (1 page each) | NSF/HCFA fixed-width | **Tier A**: clean single-page CMS-1500, no attachments |
| Group B | 5 TIFFs (2-page + 3-page bundles) | spans 2 claim bundles | NSF/HCFA fixed-width | **Tier B (corrected)**: initial visual inspection suggested page 1 = real CMS-1500 and later pages = attachments. **Running the actual classifier against real OCR text disproved this** — all 5 sample images in this batch are tracking-slip/cover-sheet pages (Unique ID, Tracking No, RecvDate fields), not a real claim form. Ground truth records still exist for these claims (same pattern as Tier D). Treat Tier B's "discard non-claim pages" logic as still correct and needed in production, but do not assume this specific sample set contains a real CMS-1500 to validate extraction against — use Group A/C for that instead. |
| Group C | 6 TIFFs | 6 (1 page each) | UB-92 fixed-width (numeric record types) | **Tier C**: clean single-page UB-04 |
| Group D | 7 TIFFs | 7 claim headers exist in ground truth | NSF/HCFA fixed-width (partially populated) | **Tier D**: **all 7 sample images are "Document Separator" barcode cover sheets with zero extractable claim content**, even though ground truth records exist (the real claim page is not present in this image set). Correct behavior = detect "no claim content" and route to reject/review, NOT attempt extraction. |

### File formats
- Claim page images: TIFF, little-endian, bi-level (1 bit/pixel), Group 4 fax compression,
  ~1700×2200px, `PhotometricInterpretation=WhiteIsZero`. File extensions are sequential page
  numbers (`.001`, `.002`, ...), not `.tif`.
- Ground truth: fixed-width text files, one file per batch, named
  `DATAMATICS_UBH_{HCFA|UB}_{date} - Group {X}.txt`.
- Two field-position specifications (legacy `.doc`, convert via LibreOffice headless or similar):
  - `NSF Matrix Version 2 15 - June 2013.doc` — defines every HCFA/NSF record type (AA0, BA0,
    BA1, CA0, DA0, DA1, DA2, EA0, FA0, FB0, ..., XA0, YA0, ZA0) with exact byte positions,
    required/conditional/optional/not-used flags, and code value tables.
  - `UB92 File Specs - February 2012.doc` — defines UB-92 record types by 2-digit numeric code
    (01 processor, 10 provider, 20 patient, 30/31 payer, 40/41 occurrence/condition codes,
    46 additional provider, 50 IP accommodations, 60 ancillary services, 61 outpatient
    procedures, 70 medical data, 78 additional dx/procedure codes, 80 physician, 90 claim
    control, 91 remarks, 95 batch control, 99 file control).

### Ground truth record structure (HCFA/NSF) — confirmed by direct inspection

```
AA0  File header (submitter data)
BA0  Batch header — Provider Data 1 (provider ID, name)
BA1  Batch header — Provider Data 2 (address)
CA0  Patient data (name, DOB, sex, student/employment status)
DA0  Insurance/payer data 1 (payer ID, claim filing indicator)
DA1  Insurance/payer data 2 (subscriber address)
EA0  Claim data (employment/accident indicators, dates)
FA0  Claim root segment / service line (repeats 01-99): service from/to date, place of
     service, procedure code, charge amount
XA0  Claim trailer
YA0  Batch trailer
ZA0  File trailer
```

Example field spec (verbatim from NSF Matrix, record FA0):
```
Field 05.0  Positions 40-47  Service From Date   (Required)
Field 06.0  Positions 48-55  Service To Date     (Required)
Field 07.0  Positions 56-57  Place Of Service    (Required)  [11=Office, 21=Inpatient, ...]
```

### Ground truth record structure (UB-92) — confirmed by direct inspection

Record types are 2-digit numeric prefixes at the start of each fixed-width line (e.g. `10`,
`20`, `30`, `40`, `60`, `70`, `78`, `80`). Group C ground truth showed record type distribution:
`10` header ×1, `101` (provider/patient variant) ×6, `300`/`310` (payer) ×12 each, `400` ×6,
`600` ×6, `700` ×6, `800` ×6, `950`/`990` (trailers) — matching 6 claims exactly.

### CMS-1500 form → NSF field mapping (verified against real sample, e.g. claim `KARYO000`)

| CMS-1500 box | Field | NSF record.field |
|---|---|---|
| 1a | Insured's ID number | BA0 segment |
| 2 | Patient name (Last, First, MI) | CA0 |
| 3 | Patient DOB / sex | CA0 |
| 4 | Insured's name | BA0/CA0 |
| 5/7 | Patient/Insured address | BA1/CA0 |
| 11 | Insured's policy/group/FECA number | DA0 |
| 21 | Diagnosis codes (ICD) | EA0 |
| 24A-J | Service line: dates, place of service, CPT/HCPCS, charges, units, rendering provider NPI | FA0 (repeats per line) |
| 25 | Federal Tax ID | BA0/DA0 |
| 28 | Total charge | Sum validation across FA0 lines |

### UB-04 form → UB-92 mapping

| UB-04 box | UB-92 record type |
|---|---|
| 1, 5, 6 | Provider info, statement period | 10 |
| 8-11 | Patient data | 20 |
| 50-55 | Payer name/plan | 30/31 |
| 31-37 | Occurrence codes/dates | 40/41 |
| 42-48 | Revenue code, description, HCPCS, service date, units, charges | 60 |
| 66-68 | Diagnosis codes | 78 |
| 76-79 | Attending/operating physician | 80 |

**Important:** the above tables are a working map, not exhaustive. When implementing the
parser, read the byte-position tables directly from the converted spec `.txt` files
programmatically rather than hand-copying every field — the specs are internally consistent
tables (`Field No. | From | To | Picture | Req | Description`) that can be regex-parsed.

---

## 4. Architecture

```
Ingest & classify → Preprocess → Template OCR (region-based) → Confidence scoring
                                                                       |
                              ┌───────────────────────────────────────┴──────────────┐
                              High confidence                         Low confidence
                              → Business rule validation              → Vision-LLM escalation (cropped region only)
                                              \                        /
                                               → Business rule validation
                                                          ↓
                                                  Human review (last resort;
                                                  corrections logged for retraining)
                                                          ↓
                                                  Structured output store (JSON/DB)
```

Page classifier also assigns a **`reject_no_content`** tag for separator/junk pages (confirmed
real case: all Group D sample images) — these skip extraction entirely and go straight to a
review/audit queue, never touching OCR or LLM calls.

Tier B pages classified as `discard_attachment` (confirmed real case: Group B pages 2-3) skip
extraction entirely as well — pure cost avoidance.

### Design principles
1. **Cheap first, escalate only when needed** — LLM calls are per-field on cropped regions, not
   per-page.
2. **Confident rejection is cheaper than confident hallucination** — junk/separator pages must
   be detected, not force-extracted.
3. **Every correction is training data** — HITL corrections feed back into template/field
   confidence tuning over time.
4. **Ground truth parsing is the foundation** — build the scorer before the extractor.

---

## 5. Technology Stack

| Layer | Tool | License/Cost |
|---|---|---|
| Language | Python 3.11+ | Free |
| Image preprocessing | Pillow, OpenCV | Free |
| OCR (template extraction) | PaddleOCR or docTR (primary), Tesseract (fallback) | Free, open-source |
| Page/tier classification | OpenCV + layout heuristics, optionally scikit-learn | Free |
| Confidence escalation | Claude API (vision) — only paid component | Paid, per-call |
| Schema/validation | Pydantic + custom business-rule checks | Free |
| Ground truth parsing | Custom fixed-width parser (built from spec files) | Free |
| Orchestration (prototype) | Python `concurrent.futures` / multiprocessing | Free |
| Orchestration (production story) | FastAPI + Celery/Redis or cloud queue (SQS) — described in architecture doc, not required to run for prototype | Free / cloud infra cost at scale |
| Storage | SQLite (prototype) → PostgreSQL (production story) | Free |
| Demo UI | Streamlit (primary), Plotly/Matplotlib for charts | Free |
| Testing | pytest | Free |

**Cost model reminder:** only vision-LLM escalation calls are a paid, metered cost. Template
OCR, classification, validation, and storage are open-source/compute-only.

---

## 6. Suggested Repository Structure

```
claims-extraction/
├── data/
│   ├── raw/                     # original TIFFs + ground truth txt files (gitignored if large)
│   └── specs/                   # converted NSF Matrix / UB-92 spec text
├── src/
│   ├── ground_truth/
│   │   ├── nsf_parser.py        # parses HCFA/NSF fixed-width ground truth
│   │   └── ub92_parser.py       # parses UB-92 fixed-width ground truth
│   ├── preprocessing/
│   │   └── image_prep.py        # deskew, denoise, binarize
│   ├── classification/
│   │   └── page_classifier.py   # tier_a / tier_c / discard_attachment / reject_no_content
│   ├── extraction/
│   │   ├── template_ocr.py      # region-based OCR per form type
│   │   ├── field_templates/     # CMS-1500 and UB-04 field-position configs (declarative)
│   │   └── llm_escalation.py    # cropped-region vision-LLM calls for low-confidence fields
│   ├── validation/
│   │   └── business_rules.py    # cross-field consistency checks
│   ├── scoring/
│   │   └── accuracy_scorer.py   # diffs extraction output vs. ground truth, per tier
│   ├── cost/
│   │   └── cost_tracker.py      # logs per-page path (template/LLM/reject) → cost rollup
│   └── pipeline.py              # orchestrates all stages end-to-end
├── ui/
│   └── streamlit_app.py
├── tests/
│   └── test_*.py                # test against known sample claims (e.g. verify Group A count=12)
├── docs/
│   ├── architecture.md
│   ├── cost_analysis.md
│   ├── accuracy_analysis.md
│   └── roadmap.md
└── README.md
```

---

## 7. Build Plan — Walking Skeleton (risk-reducing order)

**This replaces a depth-first "finish each phase completely before starting the next" plan.**
Depth-first is risky under a hard deadline: if time runs out on day 5, some phases are
complete and others don't exist at all, and there is nothing coherent to submit.

Instead, build a **thin, fully-wired, end-to-end pipeline first** — every stage present but
crude — then spend the remaining time making each stage progressively more accurate. At every
point from Day 1 onward, there is a complete, runnable, submittable system. Nothing is ever
half-missing; things are just less accurate early on and more accurate later.

### Hard coding rules (apply from the very first line of code, not added later)
1. **Never crash, never return nothing.** Every function returns either a real result or a
   clearly-tagged failure object, e.g. `{"status": "failed", "stage": "ocr", "reason": "..."}`.
   No unhandled exceptions, no silent `None`. This is what prevents a demo from dying on one
   unexpected page in front of judges.
2. **Test-driven from day one.** Write the acceptance-criteria checks below as real `pytest`
   tests *before* implementing each stage. Every later change is checked against real sample
   data in seconds, so regressions are caught immediately, not discovered the night before
   submission.
3. **Commit at every milestone**, not once at the end. If something breaks late, roll back to
   the last known-good commit instead of debugging under pressure.

### Skeleton Pass — build all six stages end-to-end, crude is fine
Goal: `python pipeline.py --input data/raw/"Group A"/M047FJFL.001` runs start to finish and
produces a JSON output, even if every stage is a stub.

| Stage | Skeleton-pass version |
|---|---|
| Ground truth parser | Hardcode-parse just enough of one record type (e.g. `CA0`) to prove the byte-position approach works on one real file |
| Page classifier | Return a single hardcoded tier guess, or a trivial rule (e.g. "has barcode-only page → reject") |
| Template OCR | Run OCR on the whole page, no region-mapping yet — just prove text comes out |
| Confidence + LLM escalation | Skip real routing; call the vision-LLM on the whole page as a placeholder |
| Validation | One trivial rule (e.g. "total charge field is non-empty") |
| Scoring + cost tracking | Print raw counts, no real diffing yet |
| Demo UI | A bare Streamlit page that just calls the pipeline and prints the JSON output |

**Acceptance criteria for the skeleton pass:** the full command runs without crashing on at
least one sample from each of Group A/B/C/D, and produces *some* structured JSON for every one
of them — including Group D pages, which should come out tagged as rejected, not crash the run.

### Depth Passes — repeat, making each stage progressively real
Once the skeleton runs end-to-end, deepen each stage in this priority order (highest score
weight and hardest dependency first):

**Depth Pass 1 — Ground truth parser, done properly**
- Programmatically extract full field-position tables from both converted specs (regex on the
  `Field No. | From | To | Picture | Req | Description` pattern).
- Parse every ground truth `.txt` file into structured JSON per claim.
- **Acceptance criteria:** Group A → exactly 12 claims, Group C → exactly 6 claims, Group B →
  5 claim records, Group D → 7 claim headers parsed (even though the images themselves are
  blank separator pages).

**Depth Pass 2 — Page classifier, done properly**
- Real detection: CMS-1500 grid vs. UB-04 grid vs. tabular attachment vs. separator/barcode-only
  vs. unknown-layout (explicit fourth+fifth category, never force-fit).
- **Acceptance criteria:** correctly tags all Group A images as `tier_a`, Group C as `tier_c`,
  Group B page 1s as `tier_a`/`tier_b_primary` and pages 2-3 as `discard_attachment`, all Group
  D images as `reject_no_content`.

**Depth Pass 3 — Template OCR, done properly**
- Anchor/label-based field extraction (find the label text, read what's near it — not fixed
  pixel coordinates, since real scans shift slightly) using the field maps in Section 3.
- Per-field confidence scoring.
- **Acceptance criteria:** extracted output structurally matches the ground truth JSON schema
  from Depth Pass 1 for a majority of required fields on Group A/C samples.

**Depth Pass 4 — Confidence-driven LLM escalation, done properly**
- Crop and send only genuinely low-confidence field regions, not whole pages.
- Tag each field with its extraction method (`template` vs `llm_escalated`) — required input for
  cost tracking.

**Depth Pass 5 — Validation, accuracy scoring, cost tracking, done properly**
- Real business rules (e.g. sum of FA0 service line charges == total charge).
- Real diff against Depth Pass 1 ground truth, per tier and combined.
- Real cost rollup from the actual run (count of template-only vs. llm_escalated vs. rejected
  pages × assumed unit costs) — not an estimate.

**Depth Pass 6 — Demo UI + deliverable packaging**
- Polished Streamlit app: upload → classify → extract → validate → score, shown live.
- Compile the 8 required deliverables using real numbers from Depth Pass 5.

### Before submission — mandatory rehearsal
Clone/copy the repo into a completely fresh folder and run the README's setup instructions
exactly as written, with no shortcuts from memory. This is what catches "works on my machine"
problems (missing dependencies, hardcoded local paths) while there is still time to fix them.

### If time runs out
Stop deepening tiers and ship what's real. **Two tiers working excellently with an honest
"not yet implemented, here's the plan" note for the rest beats four tiers half-working with
silent gaps** — judges scoring accuracy and maintainability tend to penalize silent failure far
more than an honestly-scoped partial submission.

---

## 8. Cost Model Assumptions (state explicitly in the Cost Analysis deliverable)

Only vision-LLM escalation and human review are non-negligible costs. Report the actual
template/LLM-escalated/rejected split measured from the real pipeline run on the sample set,
then extrapolate to 100M pages/year — clearly labeled as an assumption-based extrapolation, not
a guarantee.

| Path | Est. cost/page | Notes |
|---|---|---|
| Template OCR only | ~$0.001-0.002 | CPU compute only, open-source |
| LLM-escalated field(s) | ~$0.01-0.02 per escalated page | Only hits the minority of pages/fields |
| Human review | ~$0.10-0.30 per reviewed page | Most expensive line item — keep this rate low |
| Rejected (no content) | ~$0 | Detected and skipped before any extraction cost |

---

## 9. Non-goals / Constraints
- Do not attempt to force field extraction on `reject_no_content` pages — correct behavior is
  detection and routing to review, not fabrication.
- Do not treat Group A-D folder names as a reliable tier label without classifier
  confirmation — the classifier must work on any incoming page, not rely on folder structure.
- Keep the human-in-the-loop rate low by design — it is both an accuracy safety net and the
  single biggest cost driver if overused.

---

## 10. Pre-Submission Checklist ("bulletproof" gap list)

This spec describes a sound plan. A plan is not a submission. Do not consider this project
ready to submit until every item below is actually true, not just planned for.

### 10.1 Robustness beyond the happy path
- [ ] **Extraction uses anchor/label-based field detection, not fixed pixel coordinates.**
      Real-world scans shift slightly; hardcoded coordinates will silently misread fields on
      any page that doesn't exactly match our ~30 samples.
- [ ] **Rotation/skew correction is implemented and tested**, not just mentioned in the
      architecture doc. Test on artificially rotated copies of sample pages if no naturally
      skewed samples exist.
- [ ] **Handwritten/low-quality-scan handling has an explicit fallback path** — the brief
      names this directly ("cramped layouts and poor-quality scans"). Even if accuracy is
      lower here, the pipeline must not crash or silently omit fields.
- [ ] **The page classifier has a defined behavior for "none of the above"** — a page that
      isn't CMS-1500, UB-04, attachment, or separator should route to a labeled "unknown
      layout" queue, not crash or get force-fit into the nearest tier.
- [ ] **Every external call (OCR, vision-LLM, file read) has error handling** — corrupted
      TIFF, OCR returning empty string, LLM timeout/rate-limit, malformed ground truth line.
      Each failure should be logged and routed to review, and must never halt the batch.
- [ ] **The full CMS-1500 and UB-04 field maps are complete**, not just the key boxes listed
      in Section 3. Every field the ground truth format defines as Required should have a
      defined extraction rule or an explicit "not attempted" status — silent gaps quietly
      lower the accuracy score.

### 10.2 The 8 required deliverables exist as real, standalone artifacts
- [ ] Solution Architecture — diagram + written doc (not just this spec)
- [ ] Technical Design — data flow, schemas, field maps, decision logic
- [ ] Working Prototype — actually runs end-to-end on the sample set
- [ ] Cost Analysis — **real measured** template/LLM/reject split from an actual run, with the
      100M-page extrapolation clearly labeled as assumption-based
- [ ] Accuracy Analysis — real scored output per tier from the ground-truth parser, not
      estimated percentages
- [ ] Throughput Benchmark — actual timing measurements (pages/sec) on the sample set, with
      extrapolation methodology stated explicitly
- [ ] Innovation Highlights — confidence-routed escalation, junk-page rejection, self-learning
      loop, etc.
- [ ] Future Roadmap — what would change/scale for real production use

### 10.3 Reproducibility
- [ ] `requirements.txt` (or `pyproject.toml`) with pinned versions
- [ ] README with setup + run instructions that work for someone who has never seen the
      project before — assume the judges will actually try to run it
- [ ] No hardcoded local file paths; use relative paths / config

### 10.4 Compliance & maturity signals (cheap to add, easy to overlook)
- [ ] **Licensing documentation** for every open-source/commercial tool used — the brief
      explicitly requires this ("licensing implications are documented")
- [ ] A short **data-security note** in the architecture doc (encryption at rest, access
      controls, audit logging) — this is PHI-adjacent data; even a few sentences signals
      production-readiness that most hackathon teams will skip

### 10.5 Logistics — don't lose before you start
- [ ] **Team registered** at `ClaimsExtraction.Hackathon@datamatics.com` before end of day
      Tuesday, July 28, 2026
- [ ] Submission format/instructions for judging confirmed (where/how to submit before
      Sunday, August 2, 2026 deadline)

**Rule of thumb:** if any checklist item can't be pointed at as an actual file, log output, or
test result — it isn't done yet, no matter how well it's described in this spec.
