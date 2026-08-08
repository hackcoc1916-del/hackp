"""
AEGIS — In-Memory State Store
Architecture v3: Investigation backbone with state machine, shared context, memory.
"""

from models import (
    Investigation, EvidenceItem, Finding, GraphNode, GraphEdge,
    TimelineEvent, InvestigationPlan, Report, AuditEntry, PipelineProgress,
    InvestigationLead, DraftDocument, Correlation,
    SharedInvestigationContext, InvestigationMemory,
    InvestigationState, STATE_TRANSITIONS,
)

# ─── Global State ────────────────────────────────────────────

investigations: dict[str, Investigation] = {}
evidence: dict[str, EvidenceItem] = {}
findings: dict[str, Finding] = {}
graph_nodes: dict[str, GraphNode] = {}
graph_edges: dict[str, GraphEdge] = {}
timeline_events: dict[str, TimelineEvent] = {}
plans: dict[str, InvestigationPlan] = {}
reports: dict[str, Report] = {}
audit_log: list[AuditEntry] = []
pipeline_progress: dict[str, PipelineProgress] = {}

# Investigation Workflow Engine stores
leads: dict[str, InvestigationLead] = {}
draft_documents: dict[str, DraftDocument] = {}
correlations: dict[str, Correlation] = {}

# Backbone core: Shared Context + Memory
investigation_contexts: dict[str, SharedInvestigationContext] = {}
investigation_memories: dict[str, InvestigationMemory] = {}

# SSE subscribers — investigation_id → list of asyncio.Queue
sse_queues: dict[str, list] = {}


# ─── State Machine ───────────────────────────────────────────

def transition_state(inv_id: str, new_state: InvestigationState, actor: str = "backbone") -> bool:
    """Transition an investigation to a new state. Validates transition. Records memory."""
    inv = investigations.get(inv_id)
    if not inv:
        return False

    old_state = inv.state
    allowed = STATE_TRANSITIONS.get(old_state.value, [])

    # Flexible for hackathon: log warning but allow
    if new_state.value not in allowed:
        log_audit(inv_id, actor, "invalid_state_transition",
                  "investigation", inv_id,
                  f"Attempted {old_state.value} -> {new_state.value} (not in allowed: {allowed}). Allowing for demo.")

    inv.state = new_state

    # Record in investigation memory
    memory = get_or_create_memory(inv_id)
    memory.record(
        event_type="state_transition",
        actor=actor,
        description=f"State: {old_state.value} -> {new_state.value}",
        state_before=old_state.value,
        state_after=new_state.value,
    )

    log_audit(inv_id, actor, "state_transition",
              "investigation", inv_id,
              f"{old_state.value} -> {new_state.value}")

    broadcast_sse(inv_id, {
        "type": "state_changed",
        "data": {"from": old_state.value, "to": new_state.value, "actor": actor},
    })

    return True


def get_or_create_context(inv_id: str) -> SharedInvestigationContext:
    """Get or create the shared investigation context."""
    if inv_id not in investigation_contexts:
        inv = investigations.get(inv_id)
        investigation_contexts[inv_id] = SharedInvestigationContext(
            investigation_id=inv_id,
            goal=inv.goal if inv else "",
            goal_type=inv.goal_type if inv else "general",
        )
    return investigation_contexts[inv_id]


def get_or_create_memory(inv_id: str) -> InvestigationMemory:
    """Get or create the investigation memory."""
    if inv_id not in investigation_memories:
        investigation_memories[inv_id] = InvestigationMemory(investigation_id=inv_id)
    return investigation_memories[inv_id]



# ─── Helpers ─────────────────────────────────────────────────

def get_investigation(inv_id: str) -> Investigation | None:
    return investigations.get(inv_id)

def get_evidence_for_investigation(inv_id: str) -> list[EvidenceItem]:
    return [e for e in evidence.values() if e.investigation_id == inv_id]

def get_findings_for_investigation(inv_id: str) -> list[Finding]:
    return [f for f in findings.values() if f.investigation_id == inv_id]

def get_graph_for_investigation(inv_id: str) -> dict:
    """Return nodes and edges scoped to a specific investigation."""
    nodes = [n for n in graph_nodes.values() if n.investigation_id == inv_id]
    edges = [e for e in graph_edges.values() if e.investigation_id == inv_id]
    return {"nodes": nodes, "edges": edges}

def get_timeline_for_investigation(inv_id: str) -> list[TimelineEvent]:
    events = [t for t in timeline_events.values() if t.investigation_id == inv_id]
    return sorted(events, key=lambda e: e.timestamp if e.timestamp else "")

def get_audit_for_investigation(inv_id: str) -> list[AuditEntry]:
    return [a for a in audit_log if a.investigation_id == inv_id]

def get_leads_for_investigation(inv_id: str) -> list[InvestigationLead]:
    return [l for l in leads.values() if l.investigation_id == inv_id]

def get_documents_for_investigation(inv_id: str) -> list[DraftDocument]:
    return [d for d in draft_documents.values() if d.investigation_id == inv_id]

def get_correlations_for_investigation(inv_id: str) -> list[Correlation]:
    return [c for c in correlations.values() if c.investigation_id == inv_id]


# ─── Audit ───────────────────────────────────────────────────

def log_audit(
    investigation_id: str,
    actor: str,
    action: str,
    entity_type: str = "",
    entity_id: str = "",
    details: str = "",
    metadata: dict | None = None,
):
    """Append an immutable audit entry. Every action goes through here."""
    entry = AuditEntry(
        investigation_id=investigation_id,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        metadata=metadata or {},
    )
    audit_log.append(entry)
    # Also broadcast as SSE event
    broadcast_sse(investigation_id, {
        "type": "audit",
        "data": {"action": action, "actor": actor, "details": details},
    })
    return entry


# ─── SSE ─────────────────────────────────────────────────────

def broadcast_sse(inv_id: str, event: dict):
    """Push an event to all SSE subscribers for an investigation."""
    import asyncio
    for q in sse_queues.get(inv_id, []):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass
