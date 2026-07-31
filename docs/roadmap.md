# Future Roadmap

## Executive Summary

This roadmap outlines the evolution from **current prototype** (Depth Pass 3) to **enterprise-grade production system** over 18 months. The system is already functional and submission-ready; this roadmap addresses scalability, advanced features, and continuous improvement.

**Current Status**: 90% accuracy, $0.0094/page, 296 pages/hour per worker, 21 tests passing

**18-Month Vision**: 98% accuracy, $0.0025/page, 1,200 pages/hour per worker, production deployment at 100M+ pages/year

---

## Phase 1: Production Readiness (Months 1-3)

### Goal: Deploy to pilot customer with <5% human review rate

#### 1.1 Complete Field Coverage
**Status**: Core fields implemented, service lines and revenue codes newly added

**Tasks**:
- [ ] Validate service line extraction (CMS-1500 Box 24) against FA0 ground truth
- [ ] Validate revenue line extraction (UB-04 Box 42-49) against record type 60
- [ ] Add remaining CMS-1500 fields (Boxes 5-7, 9-11, 17-20, 25-33)
- [ ] Add remaining UB-04 fields (Boxes 1-7, 10-41, 50-81)
- [ ] Test charge sum validation on all 30 sample pages

**Acceptance Criteria**:
- ✅ All required fields extractable (CMS-1500: 33 boxes, UB-04: 81 boxes)
- ✅ Charge sum validation passes on 95% of pages (±1% tolerance)
- ✅ Field coverage documented in extraction map

**Effort**: 3-4 weeks, 1 engineer

---

#### 1.2 Live LLM Verification
**Status**: LLM escalation code exists but only tested with mocks

**Tasks**:
- [ ] Acquire Anthropic API key (production tier with rate limits)
- [ ] Run end-to-end test on all 18 escalated pages from sample set
- [ ] Measure actual LLM accuracy (expected 95%+, verify)
- [ ] Implement retry logic for API failures (3 retries with exponential backoff)
- [ ] Add timeout handling (10s per field, fail gracefully)
- [ ] Monitor API cost per 1000 pages (validate $0.015 assumption)

**Acceptance Criteria**:
- ✅ LLM escalation verified on real API (not mocked)
- ✅ LLM accuracy ≥95% on escalated fields
- ✅ API failure rate <1% (with retries)
- ✅ Actual cost within 10% of estimated ($0.012-0.018 per field)

**Effort**: 1-2 weeks, 1 engineer

---

#### 1.3 Enhanced Preprocessing
**Status**: Basic deskew/denoise implemented, room for improvement

**Tasks**:
- [ ] Multi-pass OCR with voting (run OCR 3 times with different configs, pick majority)
- [ ] Field-specific denoise tuning (dates vs. text vs. numeric fields)
- [ ] Rotation detection beyond ±15° (currently skipped)
- [ ] Contrast enhancement for faint scans
- [ ] Border detection and cropping (remove scan margins)

**Expected Impact**:
- Low-confidence rate: 60% → **40%** (20% fewer LLM calls)
- OCR accuracy (patient_name): 67% → **75%**
- Cost savings: ~$300K/year (at 100M pages)

**Acceptance Criteria**:
- ✅ Low-confidence rate measured <45% on sample set
- ✅ Preprocessing regression tests pass (no new failures)
- ✅ Latency increase <20% (preprocessing is 6% of total time)

**Effort**: 3-4 weeks, 1 engineer

---

#### 1.4 Production Infrastructure
**Status**: Prototype runs single-threaded on local machine

**Tasks**:
- [ ] Containerize pipeline (Docker + docker-compose)
- [ ] Deploy to AWS ECS or Kubernetes (pilot cluster)
- [ ] Set up job queue (SQS or RabbitMQ)
- [ ] Implement REST API (FastAPI) for page submission
- [ ] Add PostgreSQL for structured output storage
- [ ] Add S3/blob storage for input images
- [ ] Set up monitoring (Prometheus + Grafana dashboards)
- [ ] Implement logging pipeline (CloudWatch or ELK stack)

**Acceptance Criteria**:
- ✅ Pipeline runs as containerized service (not laptop script)
- ✅ API endpoint accepts TIFF upload, returns JSON result
- ✅ Auto-scaling works (queue depth triggers scale-up)
- ✅ Monitoring dashboard shows throughput, accuracy, cost in real-time
- ✅ 99.9% uptime SLA (pilot)

**Effort**: 6-8 weeks, 2 engineers

---

#### 1.5 Security & Compliance
**Status**: No PHI handling implemented yet

**Tasks**:
- [ ] Implement encryption at rest (AES-256 for stored images/data)
- [ ] Implement encryption in transit (TLS 1.3 for all API calls)
- [ ] Add role-based access control (RBAC)
- [ ] Implement audit logging (who extracted what, when)
- [ ] Add data retention policies (auto-delete after N days)
- [ ] PII redaction for non-production environments
- [ ] HIPAA compliance documentation
- [ ] SOC 2 audit preparation (if offering SaaS)

**Acceptance Criteria**:
- ✅ Security audit passes (internal or external)
- ✅ HIPAA compliance checklist 100% complete
- ✅ Pen-test report with no critical vulnerabilities

**Effort**: 4-6 weeks, 1 engineer + security consultant

---

### Phase 1 Milestones

| Week | Milestone | Status |
|------|-----------|--------|
| Week 4 | All CMS-1500 fields extractable | 🟡 In Progress |
| Week 6 | All UB-04 fields extractable | ⚪ Not Started |
| Week 8 | Live LLM verified | ⚪ Not Started |
| Week 10 | Enhanced preprocessing deployed | ⚪ Not Started |
| Week 12 | Pilot cluster operational on AWS | ⚪ Not Started |

---

## Phase 2: Accuracy Improvements (Months 4-6)

### Goal: Achieve 95%+ accuracy, <2% human review rate

#### 2.1 Layout-Based Classifier
**Status**: Current classifier is keyword-based (100% on sample set, may degrade on edge cases)

**Tasks**:
- [ ] Collect 5,000+ labeled pages (CMS-1500, UB-04, attachments, separators)
- [ ] Train CNN classifier (ResNet or EfficientNet backbone)
- [ ] Add handwritten text detection (separate model)
- [ ] Implement multi-page bundle handling (attachments grouped with claim)
- [ ] Add confidence scoring for classification itself

**Expected Impact**:
- Classification accuracy: 100% (sample) → **99.9%** (production)
- Handle previously-unknown form variants
- Detect handwritten fields (route to specialized LLM)

**Acceptance Criteria**:
- ✅ Classification accuracy ≥99.5% on 10K-page validation set
- ✅ Handwritten text detection precision >90%, recall >85%
- ✅ Inference latency <500ms (down from 1.8s keyword-based)

**Effort**: 8-10 weeks, 1 ML engineer + 1 data labeler

---

#### 2.2 Multi-Position Anchor Probing
**Status**: Current anchor extraction tries single band below label

**Tasks**:
- [ ] Implement multi-position probe (try 3-5 vertical offsets)
- [ ] Pick highest-confidence result among candidates
- [ ] Add horizontal sweep for same-line label-value pairs (UB-04)
- [ ] Confidence calibration (re-score based on probing results)

**Expected Impact**:
- UB-04 variable layout: force-escalated → **50% trust OCR** (cost savings)
- Patient DOB (CMS-1500): 25% → **40-50%** accuracy (still escalate, but fewer failures)

**Acceptance Criteria**:
- ✅ UB-04 anchor success rate >95% (currently 83%)
- ✅ LLM escalation rate (UB-04): 100% → <60%

**Effort**: 3-4 weeks, 1 engineer

---

#### 2.3 Active Learning Loop
**Status**: Human corrections not currently fed back to model

**Tasks**:
- [ ] Build correction UI (human reviewer can edit extracted fields)
- [ ] Log corrections with original OCR output
- [ ] Retrain field-specific confidence models monthly
- [ ] A/B test new models before production deployment
- [ ] Track accuracy improvement over time

**Expected Impact**:
- Continuous accuracy improvement: +1-2% per quarter
- Reduced human review rate as edge cases are learned

**Acceptance Criteria**:
- ✅ Correction UI deployed and in use by pilot customer
- ✅ ≥100 corrections logged per month
- ✅ Measurable accuracy improvement after 1st retrain cycle

**Effort**: 6-8 weeks, 2 engineers

---

#### 2.4 Business Rule Enhancements
**Status**: Basic validation implemented (charge sum, date logic)

**Tasks**:
- [ ] Add cross-field consistency checks:
  - Self-insured: patient name == insured name
  - Service dates within coverage period
  - Diagnosis codes match procedure codes (clinical validity)
  - Tax ID matches provider ID (lookup table)
- [ ] Add external lookups:
  - NPI validation (National Provider Identifier)
  - Place of service code validation
  - CPT/HCPCS code validation
- [ ] Implement claim-specific rules:
  - Inpatient claims must have admit/discharge dates
  - Surgical procedures require anesthesia minutes
  - Emergency room claims require occurrence code

**Expected Impact**:
- Validation failure rate: TBD → **<3%** (only genuine errors)
- Catch downstream processing errors early

**Acceptance Criteria**:
- ✅ Business rules documented in validation matrix
- ✅ ≥20 rules implemented and tested
- ✅ False-positive rate <1% (valid claims not rejected)

**Effort**: 4-6 weeks, 1 engineer

---

### Phase 2 Milestones

| Week | Milestone | Status |
|------|-----------|--------|
| Week 16 | CNN classifier trained and deployed | ⚪ Not Started |
| Week 20 | Multi-position probing live | ⚪ Not Started |
| Week 22 | Active learning loop operational | ⚪ Not Started |
| Week 24 | Enhanced business rules live | ⚪ Not Started |

---

## Phase 3: Cost Optimization (Months 7-9)

### Goal: Reduce cost per page from $0.0094 to <$0.005

#### 3.1 GPU-Accelerated OCR
**Status**: Current OCR is CPU-based Tesseract

**Tasks**:
- [ ] Integrate PaddleOCR with CUDA support
- [ ] Benchmark on GPU instances (g5.xlarge)
- [ ] Optimize batch size for throughput
- [ ] Compare accuracy: Tesseract vs. PaddleOCR
- [ ] If accuracy drops, keep Tesseract; if equal/better, switch

**Expected Impact**:
- OCR latency: 4.2s → **1.5s** (2.8x faster)
- Total latency: 7.3s → **4.6s** (template-only path)
- Throughput: 492 pages/hr → **780 pages/hr** (+59%)
- Compute cost: $0.0015 → $0.0018 (GPU premium, but higher throughput)

**Trade-off**: GPU instances cost more per hour but process more pages per hour (net savings)

**Acceptance Criteria**:
- ✅ GPU OCR throughput ≥700 pages/hr (vs. 492 CPU)
- ✅ GPU OCR accuracy within 2% of CPU OCR
- ✅ Cost per 1000 pages <$0.90 (vs. $0.68 CPU, accounting for throughput)

**Effort**: 3-4 weeks, 1 engineer

---

#### 3.2 Batch LLM Requests
**Status**: One API call per escalated field (sequential)

**Tasks**:
- [ ] Group multiple fields into single API call
- [ ] Send all low-confidence fields from one page in one request
- [ ] Parse structured JSON response (field_name: value map)
- [ ] Handle partial failures gracefully (some fields extracted, others failed)

**Expected Impact**:
- LLM API overhead: -30% (fewer HTTP round-trips)
- LLM cost: 3 fields × $0.015 = $0.045 → **1 request × $0.025 = $0.025** (saves $0.02/page)
- Annual savings: $2M (at 100M pages) → **$1.4M** (saves $600K)

**Acceptance Criteria**:
- ✅ Batch API calls working for pages with 2+ escalated fields
- ✅ Cost per escalated page reduced by ≥25%
- ✅ Accuracy maintained (no degradation from batching)

**Effort**: 2-3 weeks, 1 engineer

---

#### 3.3 Multi-Provider LLM Strategy
**Status**: Claude Sonnet 4 only (single point of failure)

**Tasks**:
- [ ] Add GPT-4V as secondary provider
- [ ] Add Azure AI Vision as tertiary provider
- [ ] Implement load balancing (route based on cost, latency, availability)
- [ ] A/B test quality across providers
- [ ] Implement automatic failover if primary is down

**Expected Impact**:
- Cost optimization: Use cheapest provider per field type
  - GPT-4o-mini (~70% cheaper than Claude) for simple numeric fields
  - Claude for complex coded fields where accuracy is critical
- Blended LLM cost: $0.015 → **$0.010** per field (33% savings)
- Improved reliability: 99.9% uptime (multi-provider redundancy)

**Acceptance Criteria**:
- ✅ ≥3 LLM providers integrated
- ✅ Provider selection logic documented and tested
- ✅ LLM cost reduced by ≥20% without accuracy loss

**Effort**: 4-5 weeks, 1 engineer

---

#### 3.4 Intelligent Caching
**Status**: No caching implemented

**Tasks**:
- [ ] Hash-based page deduplication (if same scan submitted twice, return cached result)
- [ ] Field-level caching (if same patient appears in multiple claims, cache patient_name)
- [ ] Classification caching (if page hash matches known form, skip classification)
- [ ] Implement TTL-based cache expiration (Redis or Memcached)

**Expected Impact**:
- Duplicate detection: ~5-10% of pages in production (patient resubmits)
- Cost savings: Skip extraction on duplicates → **5-10% cost reduction**
- Latency: Cached result returns in <1s (vs. 7-18s full pipeline)

**Acceptance Criteria**:
- ✅ Cache hit rate >5% on production workload
- ✅ Cache invalidation works correctly (no stale data)
- ✅ Cost per page reduced by ≥5% from caching alone

**Effort**: 2-3 weeks, 1 engineer

---

### Phase 3 Milestones

| Week | Milestone | Status |
|------|-----------|--------|
| Week 28 | GPU OCR deployed to production | ⚪ Not Started |
| Week 30 | Batch LLM requests live | ⚪ Not Started |
| Week 34 | Multi-provider LLM strategy operational | ⚪ Not Started |
| Week 36 | Intelligent caching live | ⚪ Not Started |

---

## Phase 4: Advanced Features (Months 10-12)

### Goal: Handle edge cases, expand to new form types

#### 4.1 Handwritten Field Support
**Status**: Current system assumes printed text only

**Tasks**:
- [ ] Detect handwritten vs. printed text per field (CNN or heuristic)
- [ ] Route handwritten fields to specialized OCR (Google Handwriting API or Azure)
- [ ] Fallback to LLM if handwriting OCR fails
- [ ] A/B test handwriting OCR vs. direct LLM (cost/accuracy trade-off)

**Expected Impact**:
- Handle 10-15% of real-world claims with handwritten fields
- Accuracy on handwritten: 80-90% (vs. 0% currently)

**Acceptance Criteria**:
- ✅ Handwritten detection precision >90%
- ✅ Handwritten extraction accuracy >80%
- ✅ Cost per handwritten field <$0.03 (2x normal, acceptable)

**Effort**: 6-8 weeks, 1 ML engineer

---

#### 4.2 Support for Additional Form Types
**Status**: CMS-1500 and UB-04 only

**Tasks**:
- [ ] Add CMS-1450 (institutional claims, similar to UB-04)
- [ ] Add ADA dental claim form
- [ ] Add HCFA-1500 (older version of CMS-1500, legacy scans)
- [ ] Add custom form support (configurable field templates)

**Expected Impact**:
- Expand addressable market by 20-30% (dental, institutional)

**Acceptance Criteria**:
- ✅ ≥4 form types supported
- ✅ Per-form accuracy documented and tested
- ✅ Custom form configuration documented (for customer self-service)

**Effort**: 8-10 weeks, 2 engineers

---

#### 4.3 Multi-Page Bundle Handling
**Status**: Current system processes one page at a time

**Tasks**:
- [ ] Detect page bundles (claim + attachments in same submission)
- [ ] Link attachments to parent claim (metadata tagging)
- [ ] Extract text from attachments (EOBs, supporting docs)
- [ ] Route attachments to separate storage (not billed as claim)

**Expected Impact**:
- Correctly handle Tier B pages (5/30 in sample set)
- Reduce false-positive claim extraction on attachments

**Acceptance Criteria**:
- ✅ Bundle detection accuracy >95%
- ✅ Attachments stored separately (not charged as claim)
- ✅ Parent-child linking preserved in database

**Effort**: 4-6 weeks, 1 engineer

---

#### 4.4 Real-Time Feedback API
**Status**: Extraction is async (no live feedback)

**Tasks**:
- [ ] Implement synchronous API endpoint (returns result in <30s)
- [ ] Add WebSocket support for progress updates (client sees stages in real-time)
- [ ] Implement early-exit validation (fail fast if obvious errors)
- [ ] Add "confidence preview" mode (return quick low-confidence report before full extraction)

**Expected Impact**:
- Enable interactive use cases (upload claim, see result immediately)
- Reduce perceived latency for low-volume users

**Acceptance Criteria**:
- ✅ Sync API returns result in <30s (95th percentile)
- ✅ WebSocket updates pushed every 1-2 seconds during extraction
- ✅ Early-exit validation reduces wasted processing by 5-10%

**Effort**: 3-4 weeks, 1 engineer

---

### Phase 4 Milestones

| Week | Milestone | Status |
|------|-----------|--------|
| Week 42 | Handwritten field support live | ⚪ Not Started |
| Week 46 | Additional form types deployed | ⚪ Not Started |
| Week 48 | Multi-page bundle handling operational | ⚪ Not Started |
| Week 52 | Real-time feedback API live | ⚪ Not Started |

---

## Phase 5: Self-Hosted LLM (Months 13-18)

### Goal: Eliminate LLM API costs through self-hosted model

#### 5.1 Fine-Tune Open-Source LLM
**Status**: Dependent on Claude API ($0.015/field)

**Tasks**:
- [ ] Collect 10,000+ claim pages with ground truth
- [ ] Collect 5,000+ human corrections from active learning loop
- [ ] Fine-tune Llama 3 (70B or 8B quantized) on claims data
- [ ] Benchmark accuracy vs. Claude Sonnet 4
- [ ] Optimize inference (TensorRT, quantization)

**Expected Impact**:
- LLM cost: $0.015/field → **$0.003/field** (80% reduction)
- Annual savings: $940K → **$188K** (saves $752K/year at 100M pages)
- Infrastructure cost: +$500K initial (GPUs), +$100K/year (hosting)
- **Net savings**: $652K/year after infrastructure

**Trade-off**: Large upfront investment, accuracy risk (fine-tuned model may be worse)

**Acceptance Criteria**:
- ✅ Fine-tuned model accuracy within 2% of Claude
- ✅ Inference latency <5s per field (competitive with API)
- ✅ ROI positive within 12 months

**Effort**: 12-16 weeks, 2 ML engineers

---

#### 5.2 Hybrid Self-Hosted + API Strategy
**Status**: N/A (depends on 5.1)

**Tasks**:
- [ ] Use self-hosted model for 80% of fields (simple cases)
- [ ] Use Claude API for 20% of fields (complex cases)
- [ ] Implement confidence-based routing between models
- [ ] Monitor accuracy drift over time

**Expected Impact**:
- Best of both worlds: cost savings + accuracy safety net
- LLM cost: $0.015/field → **$0.006/field** (60% reduction)

**Acceptance Criteria**:
- ✅ Blended cost <$0.008/field
- ✅ Blended accuracy ≥Claude-only accuracy

**Effort**: 4-6 weeks, 1 engineer (after 5.1 complete)

---

### Phase 5 Milestones

| Week | Milestone | Status |
|------|-----------|--------|
| Week 60 | Fine-tuned LLM trained and validated | ⚪ Not Started |
| Week 68 | Self-hosted LLM deployed to subset of production traffic | ⚪ Not Started |
| Week 72 | Hybrid strategy operational, cost savings realized | ⚪ Not Started |

---

## Summary Timeline

| Phase | Months | Key Deliverable | Status |
|-------|--------|-----------------|--------|
| **Phase 1** | 1-3 | Production deployment (pilot) | 🟡 In Progress |
| **Phase 2** | 4-6 | 95%+ accuracy, <2% human review | ⚪ Not Started |
| **Phase 3** | 7-9 | Cost <$0.005/page | ⚪ Not Started |
| **Phase 4** | 10-12 | Handwriting, new forms, bundles | ⚪ Not Started |
| **Phase 5** | 13-18 | Self-hosted LLM, 80% cost savings | ⚪ Not Started |

---

## Resource Requirements

### Team Composition

| Role | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 |
|------|---------|---------|---------|---------|---------|
| **Software Engineer** | 3 | 3 | 2 | 2 | 1 |
| **ML Engineer** | 0 | 1 | 0 | 1 | 2 |
| **Data Labeler** | 0 | 1 | 0 | 0 | 0 |
| **DevOps Engineer** | 1 | 1 | 1 | 1 | 1 |
| **Security Consultant** | 0.5 | 0 | 0 | 0 | 0 |
| **Total FTE** | **4.5** | **6** | **3** | **4** | **4** |

### Budget (Annual, USD)

| Category | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 |
|----------|---------|---------|---------|---------|---------|
| **Salaries** | $450K | $600K | $300K | $400K | $400K |
| **Cloud Infra** | $100K | $150K | $200K | $250K | $350K |
| **API Costs** | $100K | $200K | $150K | $100K | $50K |
| **Tooling/Licenses** | $20K | $30K | $30K | $30K | $30K |
| **Total** | **$670K** | **$980K** | **$680K** | **$780K** | **$830K** |

**18-Month Total**: ~$3.1M

---

## Risk Mitigation

### Technical Risks
| Risk | Mitigation |
|------|------------|
| **LLM accuracy below expectations** | Multi-provider strategy, keep human review |
| **GPU OCR slower than expected** | Keep CPU OCR as fallback, measure before switching |
| **Fine-tuned model worse than API** | Hybrid strategy (self-hosted for 80%, API for 20%) |
| **Handwriting support fails** | Clearly document limitation, offer manual review SLA |

### Business Risks
| Risk | Mitigation |
|------|------------|
| **Pilot customer churns** | Lock in 2-year contract with success metrics |
| **LLM API price increases** | Multi-provider strategy, self-hosted long-term plan |
| **Regulatory changes (HIPAA)** | Continuous compliance monitoring, annual audit |
| **Competitive entry** | Patent filing, first-mover advantage, customer lock-in |

---

## Success Metrics (18-Month Targets)

| Metric | Current | 18-Month Target |
|--------|---------|-----------------|
| **Accuracy** | 90% | **98%** |
| **Cost per Page** | $0.0094 | **$0.0025** |
| **Throughput** | 296 pages/hr | **1,200 pages/hr** |
| **Human Review Rate** | 10-15% (est.) | **<2%** |
| **Uptime** | N/A (prototype) | **99.95%** |
| **Customers** | 0 (pre-launch) | **10-15 pilot customers** |

---

## Conclusion

This roadmap transforms the current **functional prototype into an enterprise-grade production system** over 18 months, with clear milestones and success metrics at each phase.

**Key Takeaways**:
1. **Phase 1 (Months 1-3)**: Production-ready pilot deployment
2. **Phase 2-3 (Months 4-9)**: Accuracy and cost optimizations
3. **Phase 4-5 (Months 10-18)**: Advanced features and self-hosted LLM

The system is **already functional and submission-ready** — this roadmap addresses the journey from prototype to production scale.
