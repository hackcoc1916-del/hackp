# AEGIS Refactor — Investigation Backbone Architecture

## Problem

The runtime currently flows as:

```
Evidence Upload → Parallel Agents → Correlation → Leads
```

But the **designed architecture** should flow as:

```
Investigation Goal → Planner → Strategy → Human Approval
    → Capability Scheduler → Parallel Capabilities
    → Shared Investigation Context → Knowledge Graph + Timeline
    → Correlation → Discovery Engine → Lead Generator
    → Communication Generator → Human Review → Report
```

This refactor aligns implementation with the investigation-first vision without rewriting capabilities.

---

## Proposed Changes

### 1. Investigation State Machine

> [!IMPORTANT]
> Every investigation must always be in exactly one state. The UI, backend, and demo all benefit from this clarity.

#### [MODIFY] [models.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/models.py)

Replace `InvestigationStatus` with an explicit state machine:

```python
class InvestigationState(str, Enum):
    PLANNING = "planning"                    # Goal set, planner generating strategy
    AWAITING_APPROVAL = "awaiting_approval"  # Strategy ready, investigator must approve
    RUNNING = "running"                      # Backbone executing capabilities
    AWAITING_EVIDENCE = "awaiting_evidence"  # Backbone needs more evidence to proceed
    REVIEW_REQUIRED = "review_required"      # Findings ready, investigator must review
    REPORT_READY = "report_ready"            # Report generated, ready for export
    CLOSED = "closed"                        # Investigation concluded
```

Add state transition validation (can only go `PLANNING → AWAITING_APPROVAL → RUNNING → REVIEW_REQUIRED → REPORT_READY → CLOSED`).

---

### 2. Shared Investigation Context

> [!IMPORTANT]
> This is the single source of truth for the entire investigation. Every capability writes TO it. Every downstream component reads FROM it.

#### [MODIFY] [models.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/models.py)

Add a new `SharedInvestigationContext` model:

```python
class SharedInvestigationContext(BaseModel):
    """Central intelligence context — the backbone's single source of truth."""
    investigation_id: str
    goal: str
    goal_type: GoalType
    strategy: dict                           # From planner
    
    # Accumulated intelligence (capabilities write here)
    entities: list[DetectedEntity]           # All extracted entities
    relationships: list[dict]                # All discovered relationships
    locations: list[dict]                    # GPS + location intelligence
    temporal_data: list[dict]                # Timestamps and sequences
    vehicle_intelligence: list[dict]         # Vehicle analysis results
    person_intelligence: list[dict]          # Person descriptions
    document_intelligence: list[dict]        # Extracted document data
    
    # Derived intelligence (correlation + discovery write here)
    correlations: list[dict]                 # Cross-evidence links
    discoveries: list[dict]                  # Things investigator didn't ask for
    leads: list[dict]                        # Actionable next steps
    
    # Metadata
    capabilities_executed: list[str]
    confidence_scores: dict                  # Per-capability confidence
    gaps: list[str]                          # What's missing
```

#### [MODIFY] [state.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/state.py)

Add `investigation_contexts: dict[str, SharedInvestigationContext]` as a new store.

---

### 3. Discovery Engine

> [!IMPORTANT]  
> Correlation connects data. Discovery creates intelligence. Lead Generation turns intelligence into actions.

#### [NEW] [discovery.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/discovery.py)

A new module that sits between Correlation and Lead Generation. It answers: **"What did we find that the investigator didn't explicitly ask about?"**

Key responsibilities:
- **Pattern Detection**: "This vehicle appeared at 3 locations within 2 hours — that's a travel pattern"
- **Anomaly Detection**: "The timestamp says night but the image shows daylight — possible metadata tampering"
- **Missing Link Identification**: "Vehicle found but no registered owner in OSINT — possible stolen vehicle"
- **Risk Escalation**: "Weapons detected in multiple evidence items — escalate to critical"
- **Connection Expansion**: "Phone number from PDF also appears in OSINT as associated with 3 other vehicles"

Gemini prompt will generate a `discoveries` list that feeds into Lead Generation with more depth than raw correlation output.

---

### 4. Planner as Entry Point

> [!WARNING]
> The current demo-pipeline skips the planner entirely. This must change.

#### [MODIFY] [main.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/main.py)

Refactor the pipeline to follow the correct flow:

```
POST /api/investigations/{id}/analyze  (renamed from demo-pipeline)
    │
    ├── 1. Planner generates Investigation Strategy
    │       └── Which capabilities to run, in what order, with what priority
    │
    ├── 2. State → AWAITING_APPROVAL (strategy shown to investigator)
    │
    ├── 3. POST /api/strategies/{id}/approve → State → RUNNING
    │
    ├── 4. Capability Scheduler executes approved strategy
    │       └── Parallel where possible, sequential where needed
    │       └── Each capability writes to SharedInvestigationContext
    │
    ├── 5. Correlation Engine (reads from context)
    │
    ├── 6. Discovery Engine (finds what wasn't asked)
    │
    ├── 7. Lead Generator + Communication Generator (parallel)
    │
    ├── 8. State → REVIEW_REQUIRED
    │
    └── 9. Investigator reviews → State → REPORT_READY
```

The **demo-pipeline endpoint** will still exist for hackathon convenience (auto-approves strategy), but the default flow goes through human approval.

---

### 5. Rename Agents → Capabilities

> [!TIP]
> This is the easiest change with the highest presentation impact.

#### [MODIFY] [index.html](file:///c:/Users/saura/OneDrive/Desktop/hackp/aegis_landing/index.html)

| Before | After |
|---|---|
| "AI Agent Fleet" | "Intelligence Capabilities" |
| "8 Agents Ready" | "8 Capabilities Active" |
| "🔍 Vision Agent" | "🔍 Image Intelligence" |
| "🚗 Vehicle Agent" | "🚗 Vehicle Intelligence" |
| "🌐 OSINT Agent" | "🌐 Open Source Intelligence" |
| "📄 PDF Agent" | "📄 Document Intelligence" |
| "🎤 Audio Agent" | "🎤 Audio Intelligence" |
| "🎬 Video Agent" | "🎬 Video Intelligence" |
| "✉️ Comms Agent" | "✉️ Communication Services" |
| "💡 Lead Generator" | "💡 Lead Intelligence" |
| "AI Agents" nav label | "Capabilities" |

#### [MODIFY] [workspace.html](file:///c:/Users/saura/OneDrive/Desktop/hackp/aegis_landing/workspace.html)

Same renaming. "Run All Agents" → "Execute Analysis". Pipeline labels use "Capability" not "Agent".

#### [MODIFY] [main.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/main.py)

- Health endpoint: `"agents"` → `"capabilities"` in response
- SSE events: use `"capability"` terminology consistently
- Startup banner: "Capabilities" not "Agents"

---

## Updated Runtime Flow

```
Investigator
    │
    ▼
Investigation Goal
    │
    ▼
Planner (generates strategy)
    │
    ▼
Investigation Strategy
    │
    ▼
Human Approval ◄──── (Investigator reviews plan)
    │
    ▼
Capability Scheduler
    │
    ▼
┌───────────────────────────────┐
│  PARALLEL ANALYSIS            │
│                               │
│  Image Intelligence           │
│  Vehicle Intelligence         │
│  Document Intelligence        │
│  Audio Intelligence           │
│  Video Intelligence           │
│  Metadata Intelligence        │
└───────────┬───────────────────┘
            │
            ▼
Shared Investigation Context ◄── (Single source of truth)
            │
            ▼
    Knowledge Graph + Timeline
            │
            ▼
    Correlation Engine
            │
            ▼
    Discovery Engine ◄── (Finds what wasn't asked)
            │
            ▼
┌───────────────────────────────┐
│  PARALLEL SYNTHESIS           │
│                               │
│  Lead Intelligence            │
│  Communication Services       │
└───────────┬───────────────────┘
            │
            ▼
    Human Review ◄── (Investigator reviews findings)
            │
            ▼
    Report Generation
```

---

## Files Changed Summary

| File | Change Type | What Changes |
|---|---|---|
| `models.py` | MODIFY | New `InvestigationState` enum, `SharedInvestigationContext` model |
| `state.py` | MODIFY | Add context store, state transition helpers |
| `discovery.py` | **NEW** | Discovery Engine (pattern/anomaly/gap detection) |
| `main.py` | MODIFY | Planner-first pipeline, state machine transitions, rename terminology |
| `index.html` | MODIFY | Rename Agents → Capabilities, state machine display |
| `workspace.html` | MODIFY | Rename labels, add strategy review step, state indicator |

---

## Open Questions

> [!IMPORTANT]
> **State Machine Strictness**: Should the state machine be strict (reject invalid transitions with HTTP 400) or flexible (auto-transition where obvious)? For hackathon demo I recommend flexible with logging.

> [!NOTE]
> **Discovery Engine Depth**: How sophisticated should the Discovery Engine be? I'm proposing a single Gemini call that analyzes the full SharedInvestigationContext and produces "unexpected findings." Is that sufficient, or do you want rule-based pattern detection too?

## Verification Plan

### Manual Verification
1. Start server → verify startup banner shows "Capabilities" not "Agents"
2. Create investigation → verify state = `planning`
3. Upload evidence → verify state stays `planning`
4. Click "Execute Analysis" → verify Planner runs first, state = `awaiting_approval`
5. Approve strategy → verify parallel capabilities execute, state = `running`
6. Wait for pipeline → verify Discovery Engine output appears as separate section
7. Verify state = `review_required`
8. Review findings → verify state = `report_ready`
9. Generate report → verify report includes discovery insights
