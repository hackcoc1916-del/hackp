"""
AEGIS PoC — Pydantic Models
All data structures for the hackathon proof of concept.

Architecture v2: Goal-driven, backbone-centric, audit-logged.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
import uuid, datetime


# ─── Enums ───────────────────────────────────────────────────

class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class GoalType(str, Enum):
    """Structured investigation objectives — the backbone understands these."""
    IDENTIFY_PERSONS = "identify_persons"
    TRACK_MOVEMENT = "track_movement"
    FIND_RELATIONSHIPS = "find_relationships"
    LOCATE_DEVICES = "locate_devices"
    INVESTIGATE_FINANCIAL = "investigate_financial"
    IDENTIFY_VICTIMS = "identify_victims"
    IDENTIFY_VEHICLE = "identify_vehicle"
    GENERAL = "general"

class InvestigationState(str, Enum):
    """Investigation State Machine — every investigation is always in exactly one state."""
    PLANNING = "planning"                    # Goal set, backbone generating strategy
    AWAITING_APPROVAL = "awaiting_approval"  # Strategy ready, investigator must approve
    RUNNING = "running"                      # Execution engine processing capabilities
    AWAITING_EVIDENCE = "awaiting_evidence"  # Backbone needs more evidence to proceed
    REVIEW_REQUIRED = "review_required"      # Findings ready, investigator must validate
    REPORT_READY = "report_ready"            # Report generated, ready for export
    CLOSED = "closed"                        # Investigation concluded

# Valid state transitions
STATE_TRANSITIONS: dict[str, list[str]] = {
    "planning":           ["awaiting_approval", "awaiting_evidence"],
    "awaiting_approval":  ["running", "planning"],
    "running":            ["review_required", "awaiting_evidence", "planning"],
    "awaiting_evidence":  ["planning", "running"],
    "review_required":    ["report_ready", "running", "planning"],
    "report_ready":       ["closed", "running"],
    "closed":             ["planning"],  # Re-open
}

# Keep backward compat alias
InvestigationStatus = InvestigationState

class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"

class FindingStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"

class EntityType(str, Enum):
    PERSON = "Person"
    VEHICLE = "Vehicle"
    LOCATION = "Location"
    DEVICE = "Device"
    OBJECT = "Object"
    TEXT = "Text"
    DOCUMENT = "Document"
    ACCOUNT = "Account"
    PHONE_NUMBER = "PhoneNumber"
    EMAIL = "Email"
    FINANCIAL = "Financial"
    TATTOO = "Tattoo"
    ORGANIZATION = "Organization"
    NUMBER_PLATE = "NumberPlate"


# ─── Core Models ─────────────────────────────────────────────

def new_id(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:8]
    return f"{prefix}{short}" if prefix else short


class Investigation(BaseModel):
    id: str = Field(default_factory=lambda: new_id("INV-"))
    name: str = "Untitled Investigation"
    # Goal-driven: structured objective
    goal_type: GoalType = GoalType.GENERAL
    goal: str = ""                       # freetext description
    goal_parameters: dict = Field(default_factory=dict)
    expected_deliverables: list[str] = Field(default_factory=list)
    # State Machine
    state: InvestigationState = InvestigationState.PLANNING
    priority: Priority = Priority.MEDIUM
    lead_investigator: str = "SSA Sarah Chen"
    classification: str = "Law Enforcement Sensitive"
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    # References
    evidence_ids: list[str] = Field(default_factory=list)
    strategy_id: Optional[str] = None    # Current execution strategy
    plan_id: Optional[str] = None        # Legacy / planner output
    finding_ids: list[str] = Field(default_factory=list)
    report_ids: list[str] = Field(default_factory=list)

    # Backward compat
    @property
    def status(self) -> InvestigationState:
        return self.state


class EvidenceItem(BaseModel):
    id: str = Field(default_factory=lambda: new_id("EV-"))
    investigation_id: str = ""
    filename: str = ""
    mime_type: str = ""
    file_size: int = 0
    sha256: str = ""
    file_path: str = ""
    thumbnail_path: str = ""
    uploaded_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    metadata: dict = Field(default_factory=dict)
    analysis: Optional[VisionAnalysis] = None
    analysis_extra: dict = Field(default_factory=dict)  # audio, PDF, etc.


class GPSCoordinate(BaseModel):
    latitude: float
    longitude: float
    altitude: Optional[float] = None


class EvidenceMetadata(BaseModel):
    gps: Optional[GPSCoordinate] = None
    timestamp: Optional[str] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    orientation: Optional[str] = None
    software: Optional[str] = None
    raw: dict = Field(default_factory=dict)


# ─── AI Models ───────────────────────────────────────────────

class DetectedEntity(BaseModel):
    type: EntityType = EntityType.OBJECT
    description: str = ""
    confidence: float = 0.0
    details: str = ""


class VisionAnalysis(BaseModel):
    description: str = ""
    entities: list[DetectedEntity] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)
    requires_review: bool = False
    review_reason: str = ""
    reasoning: str = ""


class PlanTask(BaseModel):
    id: str = Field(default_factory=lambda: new_id("T-"))
    capability: str = ""
    description: str = ""
    rationale: str = ""
    status: TaskStatus = TaskStatus.QUEUED
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    result_summary: str = ""


class PlanPhase(BaseModel):
    name: str = ""
    tasks: list[PlanTask] = Field(default_factory=list)


class InvestigationPlan(BaseModel):
    id: str = Field(default_factory=lambda: new_id("PLN-"))
    investigation_id: str = ""
    objective: str = ""
    phases: list[PlanPhase] = Field(default_factory=list)
    capabilities_selected: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    approved: bool = False
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: new_id("FND-"))
    investigation_id: str = ""
    title: str = ""
    description: str = ""
    confidence: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)
    entities: list[DetectedEntity] = Field(default_factory=list)
    reasoning: str = ""
    alternative_hypotheses: list[str] = Field(default_factory=list)
    status: FindingStatus = FindingStatus.PENDING
    requires_review: bool = True
    review_reason: str = ""
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_notes: str = ""


class GraphNode(BaseModel):
    id: str = Field(default_factory=lambda: new_id("N-"))
    investigation_id: str = ""          # scoped to investigation
    type: EntityType = EntityType.OBJECT
    label: str = ""
    properties: dict = Field(default_factory=dict)
    confidence: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    id: str = Field(default_factory=lambda: new_id("E-"))
    investigation_id: str = ""          # scoped to investigation
    source_id: str = ""
    target_id: str = ""
    relationship: str = ""
    properties: dict = Field(default_factory=dict)
    confidence: float = 0.0


class TimelineEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("TL-"))
    investigation_id: str = ""
    timestamp: str = ""
    title: str = ""
    description: str = ""
    event_type: str = ""
    evidence_id: Optional[str] = None
    gps: Optional[GPSCoordinate] = None
    actor: str = ""                     # "backbone", "gemini", "SSA Sarah Chen"


class Report(BaseModel):
    id: str = Field(default_factory=lambda: new_id("RPT-"))
    investigation_id: str = ""
    title: str = ""
    content: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class LeadPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class LeadStatus(str, Enum):
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    COMPLETED = "completed"

class DocumentType(str, Enum):
    EMAIL_MVD = "email_mvd"              # Email to Motor Vehicle Department
    EMAIL_INFO_REQUEST = "email_info"    # General information request
    COURT_ORDER = "court_order"
    FIR_DRAFT = "fir_draft"              # First Information Report
    INTERNAL_REPORT = "internal_report"
    EVIDENCE_LOG = "evidence_log"
    WITNESS_NOTICE = "witness_notice"
    BOLO = "bolo"                        # Be On the Lookout


class InvestigationLead(BaseModel):
    """Proactive investigation lead — AI suggests what to do next."""
    id: str = Field(default_factory=lambda: new_id("LEAD-"))
    investigation_id: str = ""
    title: str = ""
    description: str = ""
    priority: LeadPriority = LeadPriority.MEDIUM
    confidence: float = 0.0
    suggested_action: str = ""           # What the investigator should do
    source_evidence_ids: list[str] = Field(default_factory=list)
    source_entity_ids: list[str] = Field(default_factory=list)
    category: str = ""                   # e.g., "vehicle_trace", "witness_interview", "cctv_review"
    status: LeadStatus = LeadStatus.SUGGESTED
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class DraftDocument(BaseModel):
    """Auto-generated official document for investigator review."""
    id: str = Field(default_factory=lambda: new_id("DOC-"))
    investigation_id: str = ""
    doc_type: DocumentType = DocumentType.INTERNAL_REPORT
    title: str = ""
    recipient: str = ""
    content: str = ""                    # Full document content (markdown)
    status: str = "draft"                # draft, reviewed, sent
    generated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class Correlation(BaseModel):
    """Cross-evidence entity correlation — links entities across evidence items."""
    id: str = Field(default_factory=lambda: new_id("COR-"))
    investigation_id: str = ""
    entity_a_id: str = ""
    entity_a_label: str = ""
    entity_b_id: str = ""
    entity_b_label: str = ""
    relationship: str = ""               # e.g., "SAME_AS", "OWNS", "CONTACTED"
    confidence: float = 0.0
    reasoning: str = ""
    evidence_chain: list[str] = Field(default_factory=list)  # evidence IDs that support this
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class VehicleAnalysis(BaseModel):
    """Specialized vehicle forensics result."""
    brand: str = ""
    model: str = ""
    color: str = ""
    year_estimate: str = ""
    registration_plate: str = ""
    plate_confidence: float = 0.0
    vehicle_type: str = ""               # SUV, sedan, truck, motorcycle, etc.
    damage: list[str] = Field(default_factory=list)
    modifications: list[str] = Field(default_factory=list)
    direction_of_travel: str = ""
    speed_estimate: str = ""


class AudioAnalysis(BaseModel):
    """Audio evidence analysis result."""
    transcript: str = ""
    speaker_count: int = 0
    keywords: list[str] = Field(default_factory=list)
    emotion: str = ""
    language: str = ""
    duration_seconds: float = 0.0
    background_sounds: list[str] = Field(default_factory=list)


class DocumentAnalysis(BaseModel):
    """PDF/document analysis result."""
    extracted_text: str = ""
    names: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    addresses: list[str] = Field(default_factory=list)
    id_numbers: list[str] = Field(default_factory=list)
    case_numbers: list[str] = Field(default_factory=list)
    phone_numbers: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    summary: str = ""


# ─── Audit Trail ─────────────────────────────────────────────

class AuditEntry(BaseModel):
    id: str = Field(default_factory=lambda: new_id("AUD-"))
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    investigation_id: str = ""
    actor: str = ""                     # "SSA Sarah Chen", "backbone", "gemini"
    action: str = ""                    # "investigation_created", "evidence_uploaded", "plan_approved", etc.
    entity_type: str = ""               # "investigation", "evidence", "finding", "plan"
    entity_id: str = ""
    details: str = ""
    metadata: dict = Field(default_factory=dict)


# ─── Pipeline Progress ──────────────────────────────────────

class PipelineProgress(BaseModel):
    """Tracks background pipeline execution progress."""
    investigation_id: str = ""
    status: str = "idle"                # "idle", "running", "complete", "failed"
    total_tasks: int = 0
    completed_tasks: int = 0
    current_task: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    results: dict = Field(default_factory=dict)


# ─── Shared Investigation Context ───────────────────────────
# The single source of truth. Every capability writes to it.
# Every downstream component reads from it.

class SharedInvestigationContext(BaseModel):
    """Central intelligence context — the backbone's single source of truth.
    
    Capabilities WRITE intelligence here.
    Correlation, Discovery, Leads READ from here.
    """
    investigation_id: str
    goal: str = ""
    goal_type: GoalType = GoalType.GENERAL
    strategy: dict = Field(default_factory=dict)         # From planner

    # Accumulated intelligence (capabilities write here)
    entities: list[dict] = Field(default_factory=list)   # All extracted entities
    relationships: list[dict] = Field(default_factory=list)
    locations: list[dict] = Field(default_factory=list)  # GPS + location intelligence
    temporal_data: list[dict] = Field(default_factory=list)
    vehicle_intelligence: list[dict] = Field(default_factory=list)
    person_intelligence: list[dict] = Field(default_factory=list)
    document_intelligence: list[dict] = Field(default_factory=list)
    audio_intelligence: list[dict] = Field(default_factory=list)

    # Derived intelligence (correlation + discovery write here)
    correlations: list[dict] = Field(default_factory=list)
    discoveries: list[dict] = Field(default_factory=list)
    leads: list[dict] = Field(default_factory=list)

    # Metadata
    capabilities_executed: list[str] = Field(default_factory=list)
    capabilities_pending: list[str] = Field(default_factory=list)
    confidence_scores: dict = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)        # What's missing

    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


# ─── Investigation Memory ───────────────────────────────────
# Different from SharedContext: context = current working state,
# memory = historical record of how the investigation evolved.

class MemoryEntry(BaseModel):
    """A single entry in the investigation's historical memory."""
    id: str = Field(default_factory=lambda: new_id("MEM-"))
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    event_type: str = ""     # "goal_set", "strategy_generated", "human_decision",
                             # "capability_result", "discovery_made", "state_transition"
    actor: str = ""          # "backbone", "investigator", capability name
    description: str = ""
    data: dict = Field(default_factory=dict)
    state_before: str = ""
    state_after: str = ""


class InvestigationMemory(BaseModel):
    """Historical record of the investigation's evolution.
    
    Unlike SharedContext (current state), Memory records every decision,
    transition, and result over time. Enables re-planning and audit.
    """
    investigation_id: str
    entries: list[MemoryEntry] = Field(default_factory=list)

    def record(self, event_type: str, actor: str, description: str,
               data: dict | None = None, state_before: str = "", state_after: str = "") -> MemoryEntry:
        entry = MemoryEntry(
            event_type=event_type, actor=actor, description=description,
            data=data or {}, state_before=state_before, state_after=state_after,
        )
        self.entries.append(entry)
        return entry


# Resolve forward references
Investigation.model_rebuild()
EvidenceItem.model_rebuild()
