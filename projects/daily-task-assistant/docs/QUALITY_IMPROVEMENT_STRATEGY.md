# DATA Quality Improvement Strategy - Phase 1: Attention

> **Created**: 2026-01-01
> **Status**: Phase 1A Complete - Collecting Baseline Data
> **Framework**: DMAIC (Define, Measure, Analyze, Improve, Control)
> **Priority Order**: Attention → Suggestions → Rules

---

## Executive Summary

DATA's email suggestions (Attention, Actions, Rules) lack quality. Users see 41 items when 3-5 would suffice. VIP matching is brittle. Feedback is collected but unused.

**Consensus from 5 AI models**: Don't optimize prompts. Instead:
1. Dynamic few-shot learning (retrieve similar accepted examples)
2. Structured JSON output with confidence scores
3. Post-LLM acceptance classifier
4. Confidence thresholds for show/suppress

---

## DMAIC Framework

### D - DEFINE: What Does Quality Mean?

| Metric | Phase 1 Target | Current State |
|--------|----------------|---------------|
| **Precision** | 80%+ of shown items are actionable | Unknown (no tracking) |
| **Acceptance Rate** | 70%+ items accepted or acted upon | Unknown |
| **False Positive Rate** | <20% dismissed as irrelevant | Unknown |
| **Signal-to-Noise** | Show 5-10 items, not 40+ | Currently ~40 church, ~3 personal |

**Quality Definition**: An attention item is "quality" if David takes action on it within 48 hours.

---

### M - MEASURE: Data Structures Evolved

#### Phase 1A Changes (Implemented 2026-01-01)

**FeedbackEntry Extended:**
```python
# NEW FIELDS added to daily_task_assistant/feedback/store.py
email_id: Optional[str] = None           # Gmail message ID
email_account: Optional[str] = None      # "church" or "personal"
suggestion_id: Optional[str] = None      # AttentionRecord or SuggestionRecord ID
analysis_method: Optional[str] = None    # "haiku", "regex", "vip", "profile_match"
confidence: Optional[float] = None       # Confidence score at time of feedback
action_taken: Optional[str] = None       # "dismissed", "task_created", "replied"
```

**AttentionRecord Extended:**
```python
# NEW FIELDS added to daily_task_assistant/email/attention_store.py
first_viewed_at: Optional[datetime] = None    # When user first saw this item
action_taken_at: Optional[datetime] = None    # When user took action
action_type: Optional[ActionType] = None      # viewed/dismissed/task_created/email_replied/ignored
suppressed_by_threshold: bool = False         # Hidden due to low confidence
user_modified_reason: bool = False            # User changed the suggested reason
```

**New API Endpoints:**
- `POST /email/attention/{account}/{email_id}/viewed` - Record first view
- `GET /email/attention/{account}/quality-metrics` - Get acceptance rates

**Frontend API Functions:**
- `markAttentionViewed()` - Call when attention item is displayed
- `getQualityMetrics()` - Fetch quality dashboard data

---

### A - ANALYZE: Infrastructure Assessment

#### Google Stack Capabilities

| Capability | Google Solution | Status |
|------------|-----------------|--------|
| **Embeddings** | Vertex AI (`gemini-embedding-001`) | Available, pay-per-use |
| **Vector Search** | Firestore Vector Search | Native since 2024 |
| **Storage** | Firestore | Already using |
| **ML Training** | Vertex AI AutoML | Available for classifier |

**Cost Estimate**: <$5/month for embedding infrastructure

---

### I - IMPROVE: Implementation Phases

| Phase | Focus | Status | Timeline |
|-------|-------|--------|----------|
| **1A** | Instrument feedback (email context linkage) | **COMPLETE** | 2026-01-01 |
| **1B** | Confidence thresholds | Pending | After 2 weeks data |
| **1E** | Quality tab (Email Management) | Pending | Parallel with 1B |
| **1D** | Few-shot retrieval | Pending | After thresholds validated |
| **1C** | Fuzzy VIP matching | Backlog | Low priority |

#### Phase 1B: Add Confidence Thresholds

**Goal:** Only show high-confidence attention items.

**Changes:**
1. Add threshold config: `DTA_ATTENTION_CONFIDENCE_THRESHOLD=0.7`
2. Filter attention items below threshold before displaying
3. Track "suppressed" items separately for analysis
4. Add threshold override in UI (show suppressed on demand)

**User Control:** Threshold must be adjustable via Dashboard Settings or hamburger menu.

#### Phase 1D: Implement Few-Shot Retrieval

**Goal:** Inject similar accepted examples into Haiku prompts.

**Configuration (from David's feedback):**
- Embedding model: `gemini-embedding-001`
- Few-shot pool size: Start with **3 examples** per category
- Content field: Use AI-generated summary if available, snippet as fallback

**New Files Required:**
- `daily_task_assistant/email/embedding_store.py`
- `daily_task_assistant/llm/few_shot_retrieval.py`

#### Phase 1E: Build Quality Dashboard

**Goal:** Visualize quality metrics for continuous improvement.

**Location:** Add "Quality" tab under Email Management (Phase 1). Future vision: Dashboard becomes DATA's landing page.

**Dashboard Shows:**
- Acceptance rate by analysis_method (haiku/regex/vip)
- Acceptance rate over time (trending up?)
- Top dismissed senders (pattern detection)
- Response latency distribution
- Confidence calibration (are high-confidence items actually accepted?)

---

### C - CONTROL: Maintaining Quality

1. **Weekly quality review**: Check dashboard metrics
2. **Threshold tuning**: Adjust confidence threshold based on data
3. **Few-shot pool curation**: Periodically clean low-quality examples
4. **Feedback loop**: "needs_work" patterns → prompt adjustments

---

## Files Modified in Phase 1A

| File | Changes |
|------|---------|
| `daily_task_assistant/feedback/store.py` | +6 fields on FeedbackEntry, updated serialization |
| `daily_task_assistant/email/attention_store.py` | +5 fields on AttentionRecord, +4 new functions |
| `api/main.py` | +6 FeedbackRequest fields, +2 new endpoints |
| `web-dashboard/src/api.ts` | +6 FeedbackRequest fields, +2 new API functions |

---

## HITL Validation Checklist

### Phase 1A Validation

- [ ] Backend starts without errors after changes
- [ ] Existing attention items load correctly (backward compatible)
- [ ] New attention items include new fields in storage
- [ ] `GET /email/attention/{account}/quality-metrics` returns valid response
- [ ] Frontend TypeScript compiles without new errors
- [ ] Existing dismiss/snooze functionality still works

### Data Collection Verification

After 1-2 days of use:
- [ ] FeedbackEntry records show email_id populated (when email context)
- [ ] AttentionRecord shows action_type populated on dismiss/task_created
- [ ] Quality metrics endpoint returns non-zero totals

---

## Success Criteria for Phase 1

| Metric | Target |
|--------|--------|
| Attention items shown | Reduced from 40 to 5-10 |
| Acceptance rate | 70%+ (vs unknown baseline) |
| VIP matching accuracy | "Gary M. Landau" matches "gary landau" |
| Quality dashboard | Live metrics visible |
| Feedback linkage | 100% of email feedback has email_id |

---

## Strategic Decisions (Confirmed)

1. **Priority**: Foundation first. VIP matching (1C) is deprioritized - proper data storage enables long-term improvement.

2. **Dashboard Location**: Phase 1 adds "Quality" tab under Email Management. Future vision has Dashboard as DATA's landing page.

3. **Approach**: Measure before optimize. Collect 2 weeks of baseline data before implementing thresholds.

4. **All thresholds**: Must be **user-manageable** via Dashboard Settings or hamburger menu.

---

## References

- **Confluence**: "2026-01-01 DATA's Quality Improvement Strategy Planning - Phase 1" (page 97189897)
- **AI Research**: Consensus from Claude Opus 4.5, Gemini 3, Perplexity, Copilot GPT-5.1, ChatGPT

---

## Document History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-01 | David + Claude Code | Phase 1A implementation complete |
