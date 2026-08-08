"""
AEGIS PoC — FastAPI Server
Architecture v2: Background processing, capability registry, goal-driven, audit-logged.

Run: uvicorn main:app --reload --port 8000
"""

from __future__ import annotations
import asyncio, hashlib, mimetypes, os, shutil, time, datetime, json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from PIL import Image

import state
from models import (
    Investigation, EvidenceItem, Finding, FindingStatus,
    InvestigationStatus, TaskStatus, TimelineEvent, Priority,
    GoalType, PipelineProgress
)
from metadata import extract_metadata
from vision import analyze_image
from planner import generate_plan
from graph import build_graph_from_evidence, get_graph_summary
from report import generate_report


# ─── Paths ───────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
THUMB_DIR = BASE_DIR / "thumbnails"
FRONTEND_DIR = BASE_DIR / "aegis_landing"

UPLOAD_DIR.mkdir(exist_ok=True)
THUMB_DIR.mkdir(exist_ok=True)


# ─── Capability Registry ────────────────────────────────────
# Maps capability names to handler functions.
# New capabilities = add an entry. Backbone discovers them automatically.

async def _cap_vision_analysis(ev: EvidenceItem, inv: Investigation) -> dict:
    """Analyze a single evidence image with Gemini Vision."""
    analysis = await analyze_image(ev.file_path)
    ev.analysis = analysis
    return {
        "entities": len(analysis.entities),
        "requires_review": analysis.requires_review,
        "description": analysis.description[:200],
    }

async def _cap_metadata_extraction(ev: EvidenceItem, inv: Investigation) -> dict:
    """Extract EXIF metadata from an evidence image."""
    if ev.metadata:  # already extracted on upload
        return {"status": "already_extracted", "has_gps": bool(ev.metadata.get("gps"))}
    parsed = extract_metadata(ev.file_path)
    ev.metadata = parsed.model_dump()
    return {"status": "extracted", "has_gps": bool(ev.metadata.get("gps"))}

async def _cap_graph_construction(ev: EvidenceItem, inv: Investigation) -> dict:
    """Build knowledge graph nodes and edges from evidence analysis."""
    build_graph_from_evidence(ev)
    summary = get_graph_summary(inv.id)
    return {"nodes": summary["total_nodes"], "edges": summary["total_edges"]}

async def _cap_threat_assessment(ev: EvidenceItem, inv: Investigation) -> dict:
    """Check vision analysis for safety flags."""
    flags = ev.analysis.safety_flags if ev.analysis else []
    return {"safety_flags": flags, "flagged": len(flags) > 0}


CAPABILITY_REGISTRY: dict[str, dict] = {
    "vision_analysis": {
        "handler": _cap_vision_analysis,
        "description": "Analyze images for objects, people, vehicles, text, scenes",
        "evidence_types": ["image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"],
    },
    "metadata_extraction": {
        "handler": _cap_metadata_extraction,
        "description": "Extract EXIF data including GPS, timestamps, camera info",
        "evidence_types": ["image/jpeg", "image/png", "image/tiff"],
    },
    "graph_construction": {
        "handler": _cap_graph_construction,
        "description": "Build knowledge graph from analysis results",
        "evidence_types": ["image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"],
    },
    "threat_assessment": {
        "handler": _cap_threat_assessment,
        "description": "Assess safety concerns and flag items for review",
        "evidence_types": ["image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"],
    },
}


# ─── App ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "="*60)
    print("  AEGIS Investigation Intelligence Platform")
    print("  Hackathon Proof of Concept -- v2.0 (Backbone Architecture)")
    print("="*60)
    print(f"  API:          http://localhost:8000/api")
    print(f"  Frontend:     http://localhost:8000")
    print(f"  Docs:         http://localhost:8000/docs")
    api_key = os.environ.get("GEMINI_API_KEY", "")
    print(f"  Gemini:       {'[OK] API key configured' if api_key else '[!!] GEMINI_API_KEY not set'}")
    print(f"  Capabilities: {len(CAPABILITY_REGISTRY)} registered")
    print("="*60 + "\n")
    yield

app = FastAPI(
    title="AEGIS Investigation Intelligence Platform",
    description="Hackathon PoC v2 — Investigation backbone with background AI processing",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── API: Investigations ─────────────────────────────────────

@app.post("/api/investigations", tags=["Investigations"])
async def create_investigation(
    name: str = Form("Untitled Investigation"),
    goal: str = Form(""),
    goal_type: str = Form("general"),
    priority: str = Form("medium"),
):
    """Create a new investigation with a structured goal."""
    inv = Investigation(
        name=name,
        goal=goal,
        goal_type=GoalType(goal_type) if goal_type in [g.value for g in GoalType] else GoalType.GENERAL,
        priority=Priority(priority) if priority in [p.value for p in Priority] else Priority.MEDIUM,
        status=InvestigationStatus.CREATED,
    )
    state.investigations[inv.id] = inv

    state.log_audit(inv.id, inv.lead_investigator, "investigation_created",
                    "investigation", inv.id,
                    f"Created '{inv.name}' with goal: {inv.goal_type.value}")

    return inv


@app.get("/api/investigations", tags=["Investigations"])
async def list_investigations():
    return list(state.investigations.values())


@app.get("/api/investigations/{inv_id}", tags=["Investigations"])
async def get_investigation(inv_id: str):
    inv = state.get_investigation(inv_id)
    if not inv:
        raise HTTPException(404, "Investigation not found")
    return inv


# ─── API: Evidence Upload ────────────────────────────────────

@app.post("/api/investigations/{inv_id}/evidence", tags=["Evidence"])
async def upload_evidence(inv_id: str, files: list[UploadFile] = File(...)):
    """Upload evidence files. Metadata extracted immediately. AI runs later."""
    inv = state.get_investigation(inv_id)
    if not inv:
        raise HTTPException(404, "Investigation not found")

    # Transition to evidence intake
    if inv.status == InvestigationStatus.CREATED:
        inv.status = InvestigationStatus.EVIDENCE_INTAKE

    results = []
    for f in files:
        # Save file
        inv_dir = UPLOAD_DIR / inv_id
        inv_dir.mkdir(exist_ok=True)
        file_path = inv_dir / f.filename
        content = await f.read()
        with open(file_path, "wb") as fp:
            fp.write(content)

        # Compute SHA-256
        sha = hashlib.sha256(content).hexdigest()

        # Generate thumbnail
        thumb_path = ""
        mime = mimetypes.guess_type(f.filename)[0] or "application/octet-stream"
        if mime.startswith("image/"):
            try:
                thumb_dir = THUMB_DIR / inv_id
                thumb_dir.mkdir(exist_ok=True)
                thumb_file = thumb_dir / f"thumb_{f.filename}"
                img = Image.open(file_path)
                img.thumbnail((300, 300))
                img.save(thumb_file, "JPEG", quality=80)
                thumb_path = str(thumb_file)
            except Exception:
                pass

        # Extract EXIF metadata immediately (no AI needed)
        meta_result = {}
        if mime.startswith("image/"):
            parsed = extract_metadata(str(file_path))
            meta_result = parsed.model_dump()

        # Create evidence record
        ev = EvidenceItem(
            investigation_id=inv_id,
            filename=f.filename,
            mime_type=mime,
            file_size=len(content),
            sha256=sha,
            file_path=str(file_path),
            thumbnail_path=thumb_path,
            metadata=meta_result,
        )
        state.evidence[ev.id] = ev
        inv.evidence_ids.append(ev.id)

        # Timeline: evidence uploaded
        tl = TimelineEvent(
            investigation_id=inv_id,
            timestamp=meta_result.get("timestamp", ev.uploaded_at),
            title=f"Evidence uploaded: {f.filename}",
            description=f"File uploaded ({mime}, {len(content)} bytes). SHA-256: {sha[:16]}...",
            event_type="evidence_uploaded",
            evidence_id=ev.id,
            gps=meta_result.get("gps"),
            actor=inv.lead_investigator,
        )
        state.timeline_events[tl.id] = tl

        # Audit
        state.log_audit(inv_id, inv.lead_investigator, "evidence_uploaded",
                        "evidence", ev.id,
                        f"{f.filename} ({mime}, {len(content)} bytes, SHA-256: {sha[:16]}...)")

        results.append(ev)

        state.broadcast_sse(inv_id, {
            "type": "evidence_uploaded",
            "data": {"id": ev.id, "filename": ev.filename, "mime_type": mime},
        })

    return {"uploaded": len(results), "evidence": results}


@app.get("/api/investigations/{inv_id}/evidence", tags=["Evidence"])
async def list_evidence(inv_id: str):
    return state.get_evidence_for_investigation(inv_id)


@app.get("/api/evidence/{ev_id}/file", tags=["Evidence"])
async def get_evidence_file(ev_id: str):
    ev = state.evidence.get(ev_id)
    if not ev:
        raise HTTPException(404, "Evidence not found")
    return FileResponse(ev.file_path, media_type=ev.mime_type, filename=ev.filename)


@app.get("/api/evidence/{ev_id}/thumbnail", tags=["Evidence"])
async def get_evidence_thumbnail(ev_id: str):
    ev = state.evidence.get(ev_id)
    if not ev or not ev.thumbnail_path:
        raise HTTPException(404, "Thumbnail not found")
    return FileResponse(ev.thumbnail_path, media_type="image/jpeg")


# ─── API: Plan ───────────────────────────────────────────────

@app.post("/api/investigations/{inv_id}/plan", tags=["Planner"])
async def create_plan(inv_id: str):
    """Generate an investigation plan. Investigator must approve before execution."""
    inv = state.get_investigation(inv_id)
    if not inv:
        raise HTTPException(404, "Investigation not found")

    evidence_items = [
        {"filename": e.filename, "mime_type": e.mime_type, "file_size": e.file_size}
        for e in state.get_evidence_for_investigation(inv_id)
    ]

    plan = await generate_plan(inv_id, inv.goal, evidence_items)
    state.plans[plan.id] = plan
    inv.plan_id = plan.id
    inv.status = InvestigationStatus.PLAN_REVIEW

    state.log_audit(inv_id, "backbone", "plan_generated",
                    "plan", plan.id,
                    f"Generated plan with {len(plan.phases)} phases, capabilities: {plan.capabilities_selected}")

    state.broadcast_sse(inv_id, {
        "type": "plan_generated",
        "data": {"plan_id": plan.id, "status": "awaiting_approval"},
    })
    return plan


@app.post("/api/plans/{plan_id}/approve", tags=["Planner"])
async def approve_plan(plan_id: str):
    """Approve the plan and trigger background pipeline execution."""
    plan = state.plans.get(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    inv = state.get_investigation(plan.investigation_id)
    if not inv:
        raise HTTPException(404, "Investigation not found")

    # Mark approved
    plan.approved = True
    plan.approved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    plan.approved_by = inv.lead_investigator

    state.log_audit(plan.investigation_id, inv.lead_investigator, "plan_approved",
                    "plan", plan_id,
                    "Investigation plan approved. Pipeline execution starting.")

    # Trigger background pipeline execution
    asyncio.create_task(_execute_pipeline_background(plan.investigation_id))

    return {
        "approved": True,
        "plan_id": plan_id,
        "message": "Plan approved. Analysis pipeline running in background.",
    }


@app.get("/api/plans/{plan_id}", tags=["Planner"])
async def get_plan(plan_id: str):
    plan = state.plans.get(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan


# ─── Background Pipeline Execution ──────────────────────────

async def _execute_pipeline_background(inv_id: str):
    """
    Execute the full analysis pipeline as a background task.
    The investigator's request returns immediately.
    Progress streams via SSE.
    """
    inv = state.get_investigation(inv_id)
    if not inv:
        return

    inv.status = InvestigationStatus.PROCESSING
    evidence_items = state.get_evidence_for_investigation(inv_id)
    image_items = [e for e in evidence_items if e.mime_type.startswith("image/")]

    # Initialize progress tracker
    total_tasks = len(image_items) * 3  # vision + graph + timeline per image
    progress = PipelineProgress(
        investigation_id=inv_id,
        status="running",
        total_tasks=total_tasks,
        started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )
    state.pipeline_progress[inv_id] = progress

    state.broadcast_sse(inv_id, {
        "type": "pipeline_started",
        "data": {"total_evidence": len(image_items), "total_tasks": total_tasks},
    })

    state.log_audit(inv_id, "backbone", "pipeline_started",
                    "investigation", inv_id,
                    f"Background pipeline started. {len(image_items)} images, {total_tasks} tasks.")

    completed = 0

    for ev in image_items:
        # ── Step 1: Vision Analysis ──
        progress.current_task = f"Vision analysis: {ev.filename}"
        state.broadcast_sse(inv_id, {
            "type": "task_started",
            "data": {"capability": "vision_analysis", "evidence_id": ev.id, "filename": ev.filename},
        })

        t0 = time.time()
        try:
            cap = CAPABILITY_REGISTRY["vision_analysis"]
            result = await cap["handler"](ev, inv)
            duration = int((time.time() - t0) * 1000)

            state.broadcast_sse(inv_id, {
                "type": "task_completed",
                "data": {
                    "capability": "vision_analysis", "evidence_id": ev.id,
                    "filename": ev.filename, "duration_ms": duration, **result,
                },
            })
        except Exception as ex:
            state.broadcast_sse(inv_id, {
                "type": "task_failed",
                "data": {"capability": "vision_analysis", "evidence_id": ev.id, "error": str(ex)},
            })

        completed += 1
        progress.completed_tasks = completed

        # ── Step 2: Graph Construction ──
        progress.current_task = f"Graph construction: {ev.filename}"
        try:
            cap = CAPABILITY_REGISTRY["graph_construction"]
            await cap["handler"](ev, inv)
        except Exception:
            pass

        completed += 1
        progress.completed_tasks = completed

        # ── Step 3: Timeline event from photo timestamp ──
        progress.current_task = f"Timeline: {ev.filename}"
        if ev.metadata.get("timestamp") and ev.analysis:
            tl = TimelineEvent(
                investigation_id=inv_id,
                timestamp=ev.metadata["timestamp"],
                title=f"Photo taken: {ev.filename}",
                description=ev.analysis.description[:200] if ev.analysis.description else "",
                event_type="photo_taken",
                evidence_id=ev.id,
                gps=ev.metadata.get("gps"),
                actor="backbone",
            )
            state.timeline_events[tl.id] = tl

        completed += 1
        progress.completed_tasks = completed

        # ── Generate Finding ──
        if ev.analysis and (ev.analysis.requires_review or ev.analysis.entities):
            finding = Finding(
                investigation_id=inv_id,
                title=f"Analysis of {ev.filename}",
                description=ev.analysis.description,
                confidence=max((e.confidence for e in ev.analysis.entities), default=0),
                evidence_ids=[ev.id],
                entities=ev.analysis.entities,
                reasoning=ev.analysis.reasoning,
                requires_review=ev.analysis.requires_review,
                review_reason=ev.analysis.review_reason,
            )
            state.findings[finding.id] = finding
            inv.finding_ids.append(finding.id)

            state.log_audit(inv_id, "gemini", "finding_generated",
                            "finding", finding.id,
                            f"{finding.title} (confidence: {finding.confidence:.0%}, review: {finding.requires_review})")

            state.broadcast_sse(inv_id, {
                "type": "finding_generated",
                "data": {"finding_id": finding.id, "title": finding.title, "confidence": finding.confidence},
            })

        # Progress update
        state.broadcast_sse(inv_id, {
            "type": "pipeline_progress",
            "data": {"completed": completed, "total": total_tasks,
                     "percent": round(completed / total_tasks * 100) if total_tasks else 0},
        })

    # Pipeline complete
    progress.status = "complete"
    progress.completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    progress.results = {
        "analyzed": len(image_items),
        "findings": len(state.get_findings_for_investigation(inv_id)),
        "graph": get_graph_summary(inv_id),
    }

    inv.status = InvestigationStatus.FINDINGS_REVIEW

    state.log_audit(inv_id, "backbone", "pipeline_completed",
                    "investigation", inv_id,
                    f"Pipeline complete. {len(image_items)} images analyzed, "
                    f"{progress.results['findings']} findings generated.")

    # Timeline: analysis complete
    tl = TimelineEvent(
        investigation_id=inv_id,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        title="AI analysis complete",
        description=f"Analyzed {len(image_items)} images. {progress.results['findings']} findings await review.",
        event_type="pipeline_complete",
        actor="backbone",
    )
    state.timeline_events[tl.id] = tl

    state.broadcast_sse(inv_id, {
        "type": "pipeline_complete",
        "data": progress.results,
    })


# ─── API: Pipeline Status ───────────────────────────────────

@app.get("/api/investigations/{inv_id}/pipeline", tags=["Pipeline"])
async def get_pipeline_status(inv_id: str):
    """Get background pipeline execution status."""
    progress = state.pipeline_progress.get(inv_id)
    if not progress:
        return {"status": "idle", "investigation_id": inv_id}
    return progress


# ─── API: Findings ───────────────────────────────────────────

@app.get("/api/investigations/{inv_id}/findings", tags=["Findings"])
async def list_findings(inv_id: str):
    return state.get_findings_for_investigation(inv_id)


@app.post("/api/findings/{finding_id}/approve", tags=["Findings"])
async def approve_finding(finding_id: str, notes: str = Form("")):
    """Investigator approves an AI finding."""
    f = state.findings.get(finding_id)
    if not f:
        raise HTTPException(404, "Finding not found")

    inv = state.get_investigation(f.investigation_id)
    actor = inv.lead_investigator if inv else "Unknown"

    f.status = FindingStatus.APPROVED
    f.reviewed_by = actor
    f.reviewed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    f.review_notes = notes

    state.log_audit(f.investigation_id, actor, "finding_approved",
                    "finding", finding_id,
                    f"Approved: {f.title}" + (f" Notes: {notes}" if notes else ""))

    state.broadcast_sse(f.investigation_id, {"type": "finding_approved", "data": {"finding_id": finding_id}})
    return f


@app.post("/api/findings/{finding_id}/reject", tags=["Findings"])
async def reject_finding(finding_id: str, notes: str = Form("")):
    """Investigator rejects an AI finding with rationale."""
    f = state.findings.get(finding_id)
    if not f:
        raise HTTPException(404, "Finding not found")

    inv = state.get_investigation(f.investigation_id)
    actor = inv.lead_investigator if inv else "Unknown"

    f.status = FindingStatus.REJECTED
    f.reviewed_by = actor
    f.reviewed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    f.review_notes = notes

    state.log_audit(f.investigation_id, actor, "finding_rejected",
                    "finding", finding_id,
                    f"Rejected: {f.title}. Reason: {notes}")

    state.broadcast_sse(f.investigation_id, {"type": "finding_rejected", "data": {"finding_id": finding_id}})
    return f


# ─── API: Knowledge Graph ───────────────────────────────────

@app.get("/api/investigations/{inv_id}/graph", tags=["Graph"])
async def get_graph(inv_id: str):
    """Get the knowledge graph scoped to this investigation."""
    graph_data = state.get_graph_for_investigation(inv_id)
    return {
        "nodes": [n.model_dump() for n in graph_data["nodes"]],
        "edges": [e.model_dump() for e in graph_data["edges"]],
        "summary": get_graph_summary(inv_id),
    }


# ─── API: Timeline ──────────────────────────────────────────

@app.get("/api/investigations/{inv_id}/timeline", tags=["Timeline"])
async def get_timeline(inv_id: str):
    return state.get_timeline_for_investigation(inv_id)


# ─── API: Report ────────────────────────────────────────────

@app.post("/api/investigations/{inv_id}/report", tags=["Report"])
async def create_report(inv_id: str):
    """Generate an investigation report."""
    inv = state.get_investigation(inv_id)
    if inv:
        inv.status = InvestigationStatus.REPORT_DRAFTING

    report = await generate_report(inv_id)

    if inv:
        inv.report_ids.append(report.id)

    state.log_audit(inv_id, "backbone", "report_generated",
                    "report", report.id, f"Report: {report.title}")

    return report


@app.get("/api/reports/{report_id}", tags=["Report"])
async def get_report(report_id: str):
    report = state.reports.get(report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return report


# ─── API: Audit Trail ───────────────────────────────────────

@app.get("/api/investigations/{inv_id}/audit", tags=["Audit"])
async def get_audit_trail(inv_id: str):
    """Get the complete audit trail for an investigation. Every action logged."""
    return state.get_audit_for_investigation(inv_id)


# ─── API: Capability Registry ───────────────────────────────

@app.get("/api/capabilities", tags=["Platform"])
async def list_capabilities():
    """List all registered capabilities. The backbone discovers these at runtime."""
    return {
        name: {
            "description": cap["description"],
            "evidence_types": cap["evidence_types"],
        }
        for name, cap in CAPABILITY_REGISTRY.items()
    }


# ─── API: SSE Events ────────────────────────────────────────

@app.get("/api/investigations/{inv_id}/events", tags=["Events"])
async def investigation_events(inv_id: str):
    """Server-Sent Events stream for real-time updates."""
    queue = asyncio.Queue(maxsize=100)
    if inv_id not in state.sse_queues:
        state.sse_queues[inv_id] = []
    state.sse_queues[inv_id].append(queue)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'data': {}})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'data': {}})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if inv_id in state.sse_queues:
                try:
                    state.sse_queues[inv_id].remove(queue)
                except ValueError:
                    pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─── API: Demo Pipeline (one-click for hackathon) ───────────

@app.post("/api/investigations/{inv_id}/demo-pipeline", tags=["Demo"])
async def demo_pipeline(inv_id: str):
    """
    DEMO ONLY: Generates plan, auto-approves, triggers background pipeline.
    In production, the investigator controls each step.
    """
    inv = state.get_investigation(inv_id)
    if not inv:
        raise HTTPException(404, "Investigation not found")

    state.log_audit(inv_id, "demo", "demo_pipeline_triggered",
                    "investigation", inv_id, "Demo mode: auto-generating and approving plan.")

    # Generate plan
    evidence_items = [
        {"filename": e.filename, "mime_type": e.mime_type, "file_size": e.file_size}
        for e in state.get_evidence_for_investigation(inv_id)
    ]
    plan = await generate_plan(inv_id, inv.goal, evidence_items)
    plan.approved = True
    plan.approved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    plan.approved_by = "demo"
    state.plans[plan.id] = plan
    inv.plan_id = plan.id

    # Trigger background pipeline
    asyncio.create_task(_execute_pipeline_background(inv_id))

    return {
        "message": "Demo pipeline started. Plan auto-approved. Analysis running in background.",
        "plan_id": plan.id,
        "track_progress": f"/api/investigations/{inv_id}/pipeline",
        "stream_events": f"/api/investigations/{inv_id}/events",
    }


# ─── Health Check ────────────────────────────────────────────

@app.get("/api/health", tags=["System"])
async def health():
    return {
        "status": "ok",
        "service": "AEGIS PoC v2",
        "architecture": "investigation_backbone",
        "capabilities": len(CAPABILITY_REGISTRY),
        "investigations": len(state.investigations),
        "evidence": len(state.evidence),
        "findings": len(state.findings),
        "graph_nodes": len(state.graph_nodes),
        "graph_edges": len(state.graph_edges),
        "audit_entries": len(state.audit_log),
    }


# ─── Static Files (Frontend) ─────────────────────────────────
# Mount at root AFTER all API routes so relative links work

if FRONTEND_DIR.exists():
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def serve_index():
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>AEGIS -- Frontend not found</h1>")

    @app.get("/{page_name}.html", response_class=HTMLResponse, include_in_schema=False)
    async def serve_page(page_name: str):
        page = FRONTEND_DIR / f"{page_name}.html"
        if page.exists():
            return HTMLResponse(page.read_text(encoding="utf-8"))
        raise HTTPException(404, f"Page {page_name}.html not found")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
