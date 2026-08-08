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

class InvestigationStatus(str, Enum):
    """Investigation lifecycle — not AI pipeline stages."""
    CREATED = "created"
    EVIDENCE_INTAKE = "evidence_intake"
    PLAN_REVIEW = "plan_review"          # AI proposed plan, investigator reviewing
    PROCESSING = "processing"            # Backbone executing approved plan (background)
    FINDINGS_REVIEW = "findings_review"  # Analysis done, investigator reviewing findings
    ACTIVE = "active"                    # Ongoing with approved findings
    REPORT_DRAFTING = "report_drafting"
    CLOSED = "closed"

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
    goal_parameters: dict = Field(default_factory=dict)  # structured params per goal type
    expected_deliverables: list[str] = Field(default_factory=list)
    # Status
    priority: Priority = Priority.MEDIUM
    status: InvestigationStatus = InvestigationStatus.CREATED
    lead_investigator: str = "SSA Sarah Chen"
    classification: str = "Law Enforcement Sensitive"
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    # References
    evidence_ids: list[str] = Field(default_factory=list)
    plan_id: Optional[str] = None
    finding_ids: list[str] = Field(default_factory=list)
    report_ids: list[str] = Field(default_factory=list)


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


# Resolve forward references
Investigation.model_rebuild()
EvidenceItem.model_rebuild()
