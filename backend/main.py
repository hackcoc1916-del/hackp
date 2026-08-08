"""
AEGIS — Investigation Intelligence Platform
Architecture v3: Investigation Backbone with Execution Engine.

Runtime Flow:
  Goal -> Planner -> Strategy -> Approval -> Execution Engine
  -> Shared Context -> Correlation -> Discovery -> Leads -> Report

Run: python -m uvicorn main:app --reload --port 8000
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
    InvestigationState, InvestigationStatus, TaskStatus, TimelineEvent,
    Priority, GoalType, PipelineProgress, InvestigationLead, DraftDocument,
    Correlation, LeadStatus, DocumentType, SharedInvestigationContext,
)
from auth import (
    Token, UserAuth, users_db, get_password_hash, verify_password, 
    create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_current_user
)
from metadata import extract_metadata
from vision import analyze_image
from planner import generate_plan
from graph import build_graph_from_evidence, get_graph_summary, add_entity_node, add_edge
from report import generate_report

# ─── Intelligence Capabilities ───────────────────────────────
from vehicle_agent import analyze_vehicles, vehicle_to_entities
from osint_agent import run_osint
from communication_agent import auto_generate_documents
from lead_generator import generate_leads
from correlation import run_correlation_engine
from discovery import run_discovery_engine
from pdf_agent import analyze_pdf, document_to_entities
from audio_agent import analyze_audio, audio_to_entities
from video_agent import analyze_video


# ─── Paths ───────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
THUMB_DIR = BASE_DIR / "thumbnails"
FRONTEND_DIR = BASE_DIR / "aegis_landing"

UPLOAD_DIR.mkdir(exist_ok=True)
THUMB_DIR.mkdir(exist_ok=True)


# ─── Capability Registry ────────────────────────────────────

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
    if ev.metadata:
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

async def _cap_vehicle_analysis(ev: EvidenceItem, inv: Investigation) -> dict:
    """Run specialized vehicle forensics on an image."""
    vehicles = await analyze_vehicles(ev.file_path)
    entities = vehicle_to_entities(vehicles)
    # Add vehicle entities to graph
    for entity in entities:
        add_entity_node(entity, ev.id, inv.id)
    return {
        "vehicles_found": len(vehicles),
        "plates_found": sum(1 for v in vehicles if v.registration_plate),
        "vehicles": [{"brand": v.brand, "model": v.model, "color": v.color, "plate": v.registration_plate} for v in vehicles],
    }

async def _cap_pdf_analysis(ev: EvidenceItem, inv: Investigation) -> dict:
    """Analyze a PDF document for investigative content."""
    analysis = await analyze_pdf(ev.file_path)
    entities = document_to_entities(analysis)
    for entity in entities:
        add_entity_node(entity, ev.id, inv.id)
    return {
        "names_found": len(analysis.names),
        "phones_found": len(analysis.phone_numbers),
        "emails_found": len(analysis.emails),
        "summary": analysis.summary[:200],
    }

async def _cap_audio_analysis(ev: EvidenceItem, inv: Investigation) -> dict:
    """Analyze audio evidence for transcript and entities."""
    analysis = await analyze_audio(ev.file_path)
    entities = audio_to_entities(analysis)
    for entity in entities:
        add_entity_node(entity, ev.id, inv.id)
    ev.analysis_extra = {"audio": analysis.model_dump()}
    return {
        "speakers": analysis.speaker_count,
        "keywords": analysis.keywords[:5],
        "language": analysis.language,
        "transcript_length": len(analysis.transcript),
    }

async def _cap_video_analysis(ev: EvidenceItem, inv: Investigation) -> dict:
    """Analyze video evidence for entities and movements."""
    analysis = await analyze_video(ev.file_path)
    ev.analysis = analysis
    return {
        "entities": len(analysis.entities),
        "requires_review": analysis.requires_review,
        "description": analysis.description[:200],
    }


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
    "vehicle_analysis": {
        "handler": _cap_vehicle_analysis,
        "description": "Specialized vehicle forensics — make, model, color, registration plate",
        "evidence_types": ["image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"],
    },
    "pdf_analysis": {
        "handler": _cap_pdf_analysis,
        "description": "Extract text, names, dates, IDs from PDF documents",
        "evidence_types": ["application/pdf"],
    },
    "audio_analysis": {
        "handler": _cap_audio_analysis,
        "description": "Transcribe and analyze audio evidence",
        "evidence_types": ["audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg", "audio/mp4", "audio/flac", "audio/aac"],
    },
    "video_analysis": {
        "handler": _cap_video_analysis,
        "description": "Analyze video for entities, movements, key moments",
        "evidence_types": ["video/mp4", "video/x-msvideo", "video/quicktime", "video/x-matroska", "video/webm"],
    },
}


# ─── App ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "="*60)
    print("  AEGIS — Investigation Intelligence Platform")
    print("  Investigation Backbone with Execution Engine")
    print("="*60)
    print(f"  API:          http://localhost:8000/api")
    print(f"  Frontend:     http://localhost:8000")
    print(f"  Docs:         http://localhost:8000/docs")
    api_key = os.environ.get("GEMINI_API_KEY", "")
    grok_key = os.environ.get("GROK_API_KEY", "")
    print(f"  Gemini:       {'[OK]' if api_key else '[!!] NOT SET'}")
    print(f"  Grok:         {'[OK]' if grok_key else '[--] Not configured'}")
    print(f"  Capabilities: {len(CAPABILITY_REGISTRY)} registered")
    print(f"  Backbone:     Planner -> Execution Engine -> Shared Context")
    print(f"                -> Correlation -> Discovery -> Leads -> Report")
    print("="*60 + "\n")
    yield

app = FastAPI(
    title="AEGIS Investigation Intelligence Platform",
    description="Investigation Backbone with Execution Engine — Goal-driven investigation workflow",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── API: Auth ──────────────────────────────────────────────────
@app.post("/api/auth/register", response_model=Token, tags=["Auth"])
async def register(user_auth: UserAuth):
    if user_auth.username in users_db:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = get_password_hash(user_auth.password)
    users_db[user_auth.username] = {
        "username": user_auth.username,
        "hashed_password": hashed_password
    }
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_auth.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/auth/token", response_model=Token, tags=["Auth"])
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = users_db.get(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# ─── API: Investigations ─────────────────────────────────────

@app.post("/api/investigations", tags=["Investigations"])
async def create_investigation(
    name: str = Form("Untitled Investigation"),
    goal: str = Form(""),
    goal_type: str = Form("general"),
    priority: str = Form("medium"),
    current_user: Annotated[dict, Depends(get_current_user)] = None,
):
    """Create a new investigation with a structured goal."""
    inv = Investigation(
        name=name,
        goal=goal,
        goal_type=GoalType(goal_type) if goal_type in [g.value for g in GoalType] else GoalType.GENERAL,
        priority=Priority(priority) if priority in [p.value for p in Priority] else Priority.MEDIUM,
        state=InvestigationState.PLANNING,
    )
    state.investigations[inv.id] = inv

    # Initialize shared context and memory
    ctx = state.get_or_create_context(inv.id)
    ctx.goal = goal
    ctx.goal_type = inv.goal_type
    memory = state.get_or_create_memory(inv.id)
    memory.record("goal_set", inv.lead_investigator,
                  f"Investigation created: {name}. Goal: {goal}",
                  {"goal_type": goal_type, "priority": priority})

    state.log_audit(inv.id, inv.lead_investigator, "investigation_created",
                    "investigation", inv.id,
                    f"Created '{inv.name}' with goal: {inv.goal_type.value}")

    return inv


@app.get("/api/investigations", tags=["Investigations"])
async def list_investigations(current_user: Annotated[dict, Depends(get_current_user)]):
    return list(state.investigations.values())


@app.get("/api/investigations/{inv_id}", tags=["Investigations"])
async def get_investigation(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    inv = state.get_investigation(inv_id)
    if not inv:
        raise HTTPException(404, "Investigation not found")
    return inv


# ─── API: Evidence Upload ────────────────────────────────────

@app.post("/api/investigations/{inv_id}/evidence", tags=["Evidence"])
async def upload_evidence(
    inv_id: str, 
    current_user: Annotated[dict, Depends(get_current_user)],
    files: list[UploadFile] = File(...)
):
    """Upload evidence files. Metadata extracted immediately. AI runs later."""
    inv = state.get_investigation(inv_id)
    if not inv:
        raise HTTPException(404, "Investigation not found")

    results = []
    for f in files:
        inv_dir = UPLOAD_DIR / inv_id
        inv_dir.mkdir(exist_ok=True)
        file_path = inv_dir / f.filename
        content = await f.read()
        with open(file_path, "wb") as fp:
            fp.write(content)

        sha = hashlib.sha256(content).hexdigest()

        # Generate thumbnail for images
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

        # Extract EXIF metadata immediately for images
        meta_result = {}
        if mime.startswith("image/"):
            try:
                parsed = extract_metadata(str(file_path))
                meta_result = parsed.model_dump()
            except Exception:
                pass

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

        tl = TimelineEvent(
            investigation_id=inv_id,
            timestamp=meta_result.get("timestamp") or ev.uploaded_at,
            title=f"Evidence uploaded: {f.filename}",
            description=f"File uploaded ({mime}, {len(content)} bytes). SHA-256: {sha[:16]}...",
            event_type="evidence_uploaded",
            evidence_id=ev.id,
            gps=meta_result.get("gps"),
            actor=inv.lead_investigator,
        )
        state.timeline_events[tl.id] = tl

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
async def list_evidence(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    return state.get_evidence_for_investigation(inv_id)


@app.get("/api/evidence/{ev_id}/file", tags=["Evidence"])
async def get_evidence_file(ev_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    ev = state.evidence.get(ev_id)
    if not ev:
        raise HTTPException(404, "Evidence not found")
    return FileResponse(ev.file_path, media_type=ev.mime_type, filename=ev.filename)


@app.get("/api/evidence/{ev_id}/thumbnail", tags=["Evidence"])
async def get_evidence_thumbnail(ev_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    ev = state.evidence.get(ev_id)
    if not ev or not ev.thumbnail_path:
        raise HTTPException(404, "Thumbnail not found")
    return FileResponse(ev.thumbnail_path, media_type="image/jpeg")


# ─── API: Plan ───────────────────────────────────────────────

@app.post("/api/investigations/{inv_id}/plan", tags=["Planner"])
async def create_plan(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
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
    state.transition_state(inv_id, InvestigationState.AWAITING_APPROVAL, "backbone")

    # Record strategy in memory
    memory = state.get_or_create_memory(inv_id)
    memory.record("strategy_generated", "backbone",
                  f"Strategy: {len(plan.phases)} phases, capabilities: {plan.capabilities_selected}",
                  {"plan_id": plan.id, "phases": len(plan.phases)})

    state.log_audit(inv_id, "backbone", "strategy_generated",
                    "plan", plan.id,
                    f"Generated strategy with {len(plan.phases)} phases, capabilities: {plan.capabilities_selected}")

    state.broadcast_sse(inv_id, {
        "type": "strategy_generated",
        "data": {"plan_id": plan.id, "state": "awaiting_approval"},
    })
    return plan


@app.post("/api/plans/{plan_id}/approve", tags=["Planner"])
async def approve_plan(plan_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Approve the plan and trigger background pipeline execution."""
    plan = state.plans.get(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    inv = state.get_investigation(plan.investigation_id)
    if not inv:
        raise HTTPException(404, "Investigation not found")

    plan.approved = True
    plan.approved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    plan.approved_by = inv.lead_investigator

    state.transition_state(plan.investigation_id, InvestigationState.RUNNING, inv.lead_investigator)

    # Record investigator decision in memory
    memory = state.get_or_create_memory(plan.investigation_id)
    memory.record("human_decision", inv.lead_investigator,
                  "Strategy approved. Execution engine starting.",
                  {"plan_id": plan_id, "decision": "approved"})

    asyncio.create_task(_execute_pipeline_background(plan.investigation_id))

    return {
        "approved": True,
        "plan_id": plan_id,
        "message": "Strategy approved. Execution engine running in background.",
    }


@app.get("/api/plans/{plan_id}", tags=["Planner"])
async def get_plan(plan_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    plan = state.plans.get(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan


# ─── Execution Engine ────────────────────────────────────────

async def _execute_pipeline_background(inv_id: str):
    """
    AEGIS Execution Engine — backbone-driven investigation pipeline.
    
    Runtime Flow:
    1. Parallel Capability Execution (per evidence item)
       - Image Intelligence    - Vehicle Intelligence
       - Document Intelligence - Audio Intelligence
       - Video Intelligence    - Metadata Intelligence
    2. Shared Investigation Context (populate)
    3. Knowledge Graph + Timeline
    4. Open Source Intelligence
    5. Correlation Engine
    6. Discovery Engine (finds what wasn't asked)
    7. Lead Intelligence + Communication Services (parallel)
    8. State -> REVIEW_REQUIRED
    """
    inv = state.get_investigation(inv_id)
    if not inv:
        return

    # Ensure state is RUNNING
    if inv.state != InvestigationState.RUNNING:
        state.transition_state(inv_id, InvestigationState.RUNNING, "backbone")

    # Get shared context
    ctx = state.get_or_create_context(inv_id)
    memory = state.get_or_create_memory(inv_id)
    evidence_items = state.get_evidence_for_investigation(inv_id)

    # Categorize evidence by type
    image_items = [e for e in evidence_items if e.mime_type.startswith("image/")]
    pdf_items = [e for e in evidence_items if e.mime_type == "application/pdf"]
    audio_items = [e for e in evidence_items if e.mime_type.startswith("audio/")]
    video_items = [e for e in evidence_items if e.mime_type.startswith("video/")]

    # Calculate total tasks
    total_tasks = (
        len(image_items) * 3 +  # vision + vehicle + graph per image
        len(pdf_items) +         # pdf analysis
        len(audio_items) +       # audio analysis
        len(video_items) +       # video analysis
        3                        # osint + correlation + leads
    )

    progress = PipelineProgress(
        investigation_id=inv_id,
        status="running",
        total_tasks=max(total_tasks, 1),
        started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )
    state.pipeline_progress[inv_id] = progress

    state.broadcast_sse(inv_id, {
        "type": "pipeline_started",
        "data": {
            "total_evidence": len(evidence_items),
            "total_tasks": total_tasks,
            "capabilities": ["image_intelligence", "vehicle_intelligence", "metadata",
                             "document_intelligence", "audio_intelligence", "video_intelligence",
                             "osint", "correlation", "discovery", "leads"],
        },
    })

    state.log_audit(inv_id, "backbone", "execution_started",
                    "investigation", inv_id,
                    f"Execution engine started. {len(evidence_items)} evidence items, {total_tasks} tasks.")
    memory.record("capability_result", "backbone",
                  f"Execution engine started with {len(evidence_items)} evidence items")

    completed = 0

    # ════════════════════════════════════════════════════════════
    # PHASE 1: Parallel Capability Execution
    # ════════════════════════════════════════════════════════════

    state.broadcast_sse(inv_id, {"type": "phase_started", "data": {"phase": "Capability Execution", "phase_number": 1}})

    # Process images: Vision + Vehicle in parallel per image
    for ev in image_items:
        progress.current_task = f"Analyzing image: {ev.filename}"
        state.broadcast_sse(inv_id, {
            "type": "task_started",
            "data": {"capability": "multi_agent", "evidence_id": ev.id, "filename": ev.filename,
                     "agents": ["vision", "vehicle", "metadata"]},
        })

        t0 = time.time()

        # Run vision + vehicle analysis in PARALLEL
        try:
            vision_task = asyncio.create_task(_safe_run(_cap_vision_analysis, ev, inv, "vision_analysis"))
            vehicle_task = asyncio.create_task(_safe_run(_cap_vehicle_analysis, ev, inv, "vehicle_analysis"))

            vision_result, vehicle_result = await asyncio.gather(vision_task, vehicle_task)

            duration = int((time.time() - t0) * 1000)

            state.broadcast_sse(inv_id, {
                "type": "task_completed",
                "data": {
                    "capability": "multi_agent", "evidence_id": ev.id,
                    "filename": ev.filename, "duration_ms": duration,
                    "vision": vision_result, "vehicle": vehicle_result,
                },
            })
        except Exception as ex:
            state.broadcast_sse(inv_id, {
                "type": "task_failed",
                "data": {"capability": "multi_agent", "evidence_id": ev.id, "error": str(ex)},
            })

        completed += 2
        progress.completed_tasks = completed

        # Graph construction
        try:
            await _cap_graph_construction(ev, inv)
        except Exception:
            pass
        completed += 1
        progress.completed_tasks = completed

        # Generate Finding from vision analysis
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

            state.broadcast_sse(inv_id, {
                "type": "finding_generated",
                "data": {"finding_id": finding.id, "title": finding.title, "confidence": finding.confidence},
            })

        # Timeline from photo timestamp
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

        # Progress update
        _broadcast_progress(inv_id, completed, total_tasks)

    # Process PDFs in parallel
    if pdf_items:
        state.broadcast_sse(inv_id, {"type": "task_started", "data": {"capability": "pdf_analysis", "count": len(pdf_items)}})
        pdf_tasks = [_safe_run(_cap_pdf_analysis, ev, inv, "pdf_analysis") for ev in pdf_items]
        await asyncio.gather(*pdf_tasks)
        completed += len(pdf_items)
        progress.completed_tasks = completed
        _broadcast_progress(inv_id, completed, total_tasks)

    # Process audio files
    for ev in audio_items:
        progress.current_task = f"Analyzing audio: {ev.filename}"
        state.broadcast_sse(inv_id, {"type": "task_started", "data": {"capability": "audio_analysis", "filename": ev.filename}})
        try:
            await _cap_audio_analysis(ev, inv)
        except Exception:
            pass
        completed += 1
        progress.completed_tasks = completed
        _broadcast_progress(inv_id, completed, total_tasks)

    # Process video files
    for ev in video_items:
        progress.current_task = f"Analyzing video: {ev.filename}"
        state.broadcast_sse(inv_id, {"type": "task_started", "data": {"capability": "video_analysis", "filename": ev.filename}})
        try:
            await _cap_video_analysis(ev, inv)
            # Build graph from video analysis
            if ev.analysis:
                build_graph_from_evidence(ev)
                # Generate finding
                finding = Finding(
                    investigation_id=inv_id,
                    title=f"Video Analysis: {ev.filename}",
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
        except Exception:
            pass
        completed += 1
        progress.completed_tasks = completed
        _broadcast_progress(inv_id, completed, total_tasks)

    # ════════════════════════════════════════════════════════════
    # PHASE 2: OSINT Intelligence
    # ════════════════════════════════════════════════════════════

    state.broadcast_sse(inv_id, {"type": "phase_started", "data": {"phase": "OSINT Intelligence", "phase_number": 2}})
    progress.current_task = "Running OSINT intelligence gathering"

    # Gather all entities from graph
    all_entities = [
        {"type": n.type.value, "description": n.label, "confidence": n.confidence, "details": str(n.properties)}
        for n in state.graph_nodes.values() if n.investigation_id == inv_id
    ]

    osint_data = None
    if all_entities:
        try:
            osint_data = await run_osint(inv.goal, all_entities[:20])  # Limit to top 20 entities
            state.broadcast_sse(inv_id, {
                "type": "osint_complete",
                "data": {
                    "reports": len(osint_data.get("intelligence_reports", [])),
                    "connections": len(osint_data.get("cross_entity_connections", [])),
                },
            })
        except Exception as ex:
            state.broadcast_sse(inv_id, {"type": "osint_failed", "data": {"error": str(ex)}})

    completed += 1
    progress.completed_tasks = completed
    _broadcast_progress(inv_id, completed, total_tasks)

    # ════════════════════════════════════════════════════════════
    # PHASE 3: Correlation Engine
    # ════════════════════════════════════════════════════════════

    state.broadcast_sse(inv_id, {"type": "phase_started", "data": {"phase": "Correlation Analysis", "phase_number": 3}})
    progress.current_task = "Running cross-evidence correlation engine"

    try:
        correlations = await run_correlation_engine(inv_id, inv.goal, osint_data)
        for cor in correlations:
            state.correlations[cor.id] = cor

        state.broadcast_sse(inv_id, {
            "type": "correlation_complete",
            "data": {"correlations_found": len(correlations)},
        })
    except Exception as ex:
        state.broadcast_sse(inv_id, {"type": "correlation_failed", "data": {"error": str(ex)}})

    completed += 1
    progress.completed_tasks = completed
    _broadcast_progress(inv_id, completed, total_tasks)

    # ════════════════════════════════════════════════════════════
    # PHASE 4: Discovery Engine (finds what wasn't asked)
    # ════════════════════════════════════════════════════════════

    state.broadcast_sse(inv_id, {"type": "phase_started", "data": {"phase": "Discovery Engine", "phase_number": 4}})
    progress.current_task = "Discovery Engine — finding what wasn't asked"

    # Populate shared context before discovery
    ctx.entities = [
        {"type": n.type.value, "description": n.label, "confidence": n.confidence, "details": str(n.properties)}
        for n in state.graph_nodes.values() if n.investigation_id == inv_id
    ]
    ctx.vehicle_intelligence = [
        e.analysis_extra.get("vehicle", {}) for e in evidence_items
        if e.analysis_extra.get("vehicle")
    ]
    ctx.person_intelligence = [
        {"type": n.type.value, "description": n.label, "confidence": n.confidence}
        for n in state.graph_nodes.values()
        if n.investigation_id == inv_id and n.type.value == "Person"
    ]
    ctx.locations = [
        {"description": n.label, "gps": n.properties.get("gps", "N/A")}
        for n in state.graph_nodes.values()
        if n.investigation_id == inv_id and n.type.value == "Location"
    ]
    ctx.correlations = [
        {"entity_a_label": c.entity_a_label, "entity_b_label": c.entity_b_label,
         "relationship": c.relationship, "confidence": c.confidence, "reasoning": c.reasoning}
        for c in state.correlations.values() if c.investigation_id == inv_id
    ]
    ctx.capabilities_executed = ["image_intelligence", "vehicle_intelligence", "metadata",
                                 "osint", "correlation"]

    try:
        discovery_result = await run_discovery_engine(ctx)
        discoveries_count = len(discovery_result.get("discoveries", []))
        risk_level = discovery_result.get("risk_assessment", {}).get("overall_threat_level", "unknown")

        # Record discoveries in memory
        memory.record("discovery_made", "discovery_engine",
                      f"Found {discoveries_count} discoveries. Risk: {risk_level}",
                      {"discoveries_count": discoveries_count, "risk_level": risk_level})

        state.broadcast_sse(inv_id, {
            "type": "discovery_complete",
            "data": {
                "discoveries_found": discoveries_count,
                "risk_level": risk_level,
                "patterns": len(discovery_result.get("patterns", [])),
                "gaps_identified": len(discovery_result.get("investigation_gaps", [])),
            },
        })
    except Exception as ex:
        state.broadcast_sse(inv_id, {"type": "discovery_failed", "data": {"error": str(ex)}})

    completed += 1
    progress.completed_tasks = completed
    _broadcast_progress(inv_id, completed, total_tasks)

    # ════════════════════════════════════════════════════════════
    # PHASE 5: Lead Intelligence & Communication Services (parallel)
    # ════════════════════════════════════════════════════════════

    state.broadcast_sse(inv_id, {"type": "phase_started", "data": {"phase": "Intelligence Synthesis", "phase_number": 5}})
    progress.current_task = "Generating leads and drafting documents"

    # Prepare context for leads and documents
    inv_context = {
        "id": inv.id, "name": inv.name, "goal": inv.goal,
        "lead_investigator": inv.lead_investigator,
        "classification": inv.classification,
        "priority": inv.priority.value,
    }

    evidence_dicts = [
        {"filename": e.filename, "mime_type": e.mime_type, "sha256": e.sha256,
         "gps": str(e.metadata.get("gps", "N/A")), "timestamp": e.metadata.get("timestamp", "N/A")}
        for e in evidence_items
    ]

    entities_dicts = [
        {"type": n.type.value, "description": n.label, "confidence": n.confidence, "details": str(n.properties)}
        for n in state.graph_nodes.values() if n.investigation_id == inv_id
    ]

    findings_dicts = [
        {"title": f.title, "description": f.description, "confidence": f.confidence}
        for f in state.get_findings_for_investigation(inv_id)
    ]

    timeline_dicts = [
        {"timestamp": t.timestamp, "title": t.title, "description": t.description}
        for t in state.get_timeline_for_investigation(inv_id)
    ]

    # Run lead generation and document drafting IN PARALLEL
    try:
        leads_task = asyncio.create_task(
            generate_leads(inv_context, evidence_dicts, entities_dicts, findings_dicts, osint_data)
        )
        docs_task = asyncio.create_task(
            auto_generate_documents(inv_context, entities_dicts, findings_dicts, evidence_dicts, timeline_dicts)
        )

        leads_result, docs_result = await asyncio.gather(leads_task, docs_task)

        # Store leads
        for lead in leads_result:
            state.leads[lead.id] = lead

        # Store documents
        for doc in docs_result:
            state.draft_documents[doc.id] = doc

        state.broadcast_sse(inv_id, {
            "type": "synthesis_complete",
            "data": {
                "leads_generated": len(leads_result),
                "documents_drafted": len(docs_result),
            },
        })

    except Exception as ex:
        state.broadcast_sse(inv_id, {"type": "synthesis_failed", "data": {"error": str(ex)}})

    completed += 1
    progress.completed_tasks = completed

    # ════════════════════════════════════════════════════════════
    # PIPELINE COMPLETE
    # ════════════════════════════════════════════════════════════

    progress.status = "complete"
    progress.completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    progress.results = {
        "analyzed": len(evidence_items),
        "findings": len(state.get_findings_for_investigation(inv_id)),
        "graph": get_graph_summary(inv_id),
        "leads": len(state.get_leads_for_investigation(inv_id)),
        "documents": len(state.get_documents_for_investigation(inv_id)),
        "correlations": len(state.get_correlations_for_investigation(inv_id)),
        "discoveries": len(ctx.discoveries),
    }

    # State Machine: RUNNING -> REVIEW_REQUIRED
    state.transition_state(inv_id, InvestigationState.REVIEW_REQUIRED, "backbone")
    memory.record("capability_result", "backbone",
                  f"Execution complete. {progress.results['findings']} findings, "
                  f"{progress.results['leads']} leads, {progress.results['discoveries']} discoveries.",
                  progress.results)

    state.log_audit(inv_id, "backbone", "execution_complete",
                    "investigation", inv_id,
                    f"Execution engine complete. {len(evidence_items)} items analyzed, "
                    f"{progress.results['findings']} findings, "
                    f"{progress.results['leads']} leads, "
                    f"{progress.results['discoveries']} discoveries.")

    # Timeline: analysis complete
    tl = TimelineEvent(
        investigation_id=inv_id,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        title="Investigation analysis complete",
        description=f"Analyzed {len(evidence_items)} items. {progress.results['findings']} findings, "
                    f"{progress.results['leads']} leads, {progress.results['discoveries']} discoveries.",
        event_type="pipeline_complete",
        actor="backbone",
    )
    state.timeline_events[tl.id] = tl

    state.broadcast_sse(inv_id, {
        "type": "pipeline_complete",
        "data": progress.results,
    })


async def _safe_run(handler, ev, inv, cap_name):
    """Run a capability handler safely, catching all exceptions."""
    try:
        return await handler(ev, inv)
    except Exception as ex:
        state.broadcast_sse(inv.id, {
            "type": "task_failed",
            "data": {"capability": cap_name, "evidence_id": ev.id, "error": str(ex)},
        })
        return {"error": str(ex)}


def _broadcast_progress(inv_id, completed, total):
    """Send pipeline progress update via SSE."""
    state.broadcast_sse(inv_id, {
        "type": "pipeline_progress",
        "data": {"completed": completed, "total": total,
                 "percent": round(completed / total * 100) if total else 0},
    })


# ─── API: Pipeline Status ───────────────────────────────────

@app.get("/api/investigations/{inv_id}/pipeline", tags=["Pipeline"])
async def get_pipeline_status(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Get background pipeline execution status."""
    progress = state.pipeline_progress.get(inv_id)
    if not progress:
        return {"status": "idle", "investigation_id": inv_id}
    return progress


# ─── API: Findings ───────────────────────────────────────────

@app.get("/api/investigations/{inv_id}/findings", tags=["Findings"])
async def list_findings(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    return state.get_findings_for_investigation(inv_id)


@app.post("/api/findings/{finding_id}/approve", tags=["Findings"])
async def approve_finding(finding_id: str, notes: str = Form(""), current_user: Annotated[dict, Depends(get_current_user)] = None):
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
async def reject_finding(finding_id: str, notes: str = Form(""), current_user: Annotated[dict, Depends(get_current_user)] = None):
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


# ─── API: Investigation Leads ───────────────────────────────

@app.get("/api/investigations/{inv_id}/leads", tags=["Leads"])
async def list_leads(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Get all investigation leads (AI-suggested next actions)."""
    return state.get_leads_for_investigation(inv_id)


@app.post("/api/leads/{lead_id}/accept", tags=["Leads"])
async def accept_lead(lead_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Investigator accepts an AI-suggested lead."""
    lead = state.leads.get(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    lead.status = LeadStatus.ACCEPTED
    state.log_audit(lead.investigation_id, "investigator", "lead_accepted",
                    "lead", lead_id, f"Accepted: {lead.title}")
    return lead


@app.post("/api/leads/{lead_id}/dismiss", tags=["Leads"])
async def dismiss_lead(lead_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Investigator dismisses an AI-suggested lead."""
    lead = state.leads.get(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    lead.status = LeadStatus.DISMISSED
    state.log_audit(lead.investigation_id, "investigator", "lead_dismissed",
                    "lead", lead_id, f"Dismissed: {lead.title}")
    return lead


@app.post("/api/leads/{lead_id}/complete", tags=["Leads"])
async def complete_lead(lead_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Mark a lead as completed."""
    lead = state.leads.get(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    lead.status = LeadStatus.COMPLETED
    state.log_audit(lead.investigation_id, "investigator", "lead_completed",
                    "lead", lead_id, f"Completed: {lead.title}")
    return lead


# ─── API: Draft Documents ───────────────────────────────────

@app.get("/api/investigations/{inv_id}/documents", tags=["Documents"])
async def list_documents(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Get all auto-generated documents for an investigation."""
    return state.get_documents_for_investigation(inv_id)


@app.get("/api/documents/{doc_id}", tags=["Documents"])
async def get_document(doc_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    doc = state.draft_documents.get(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@app.post("/api/documents/{doc_id}/review", tags=["Documents"])
async def mark_document_reviewed(doc_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Mark a document as reviewed by the investigator."""
    doc = state.draft_documents.get(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    doc.status = "reviewed"
    return doc


# ─── API: Correlations ──────────────────────────────────────

@app.get("/api/investigations/{inv_id}/correlations", tags=["Correlations"])
async def list_correlations(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Get all cross-evidence entity correlations."""
    return state.get_correlations_for_investigation(inv_id)


# ─── API: Discoveries ───────────────────────────────────────

@app.get("/api/investigations/{inv_id}/discoveries", tags=["Discoveries"])
async def list_discoveries(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Get all discoveries generated by the Discovery Engine."""
    ctx = state.investigation_contexts.get(inv_id)
    if not ctx:
        return []
    return ctx.discoveries


# ─── API: Knowledge Graph ───────────────────────────────────

@app.get("/api/investigations/{inv_id}/graph", tags=["Graph"])
async def get_graph(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Get the knowledge graph scoped to this investigation."""
    graph_data = state.get_graph_for_investigation(inv_id)
    return {
        "nodes": [n.model_dump() for n in graph_data["nodes"]],
        "edges": [e.model_dump() for e in graph_data["edges"]],
        "summary": get_graph_summary(inv_id),
    }


# ─── API: Timeline ──────────────────────────────────────────

@app.get("/api/investigations/{inv_id}/timeline", tags=["Timeline"])
async def get_timeline(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    return state.get_timeline_for_investigation(inv_id)


# ─── API: Report ────────────────────────────────────────────

@app.post("/api/investigations/{inv_id}/report", tags=["Report"])
async def create_report(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
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
async def get_report(report_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    report = state.reports.get(report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return report


# ─── API: Audit Trail ───────────────────────────────────────

@app.get("/api/investigations/{inv_id}/audit", tags=["Audit"])
async def get_audit_trail(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Get the complete audit trail for an investigation. Every action logged."""
    return state.get_audit_for_investigation(inv_id)


# ─── API: Capability Registry ───────────────────────────────

@app.get("/api/capabilities", tags=["Platform"])
async def list_capabilities(current_user: Annotated[dict, Depends(get_current_user)]):
    """List all registered capabilities. The backbone discovers these at runtime."""
    return {
        name: {
            "description": cap["description"],
            "evidence_types": cap["evidence_types"],
        }
        for name, cap in CAPABILITY_REGISTRY.items()
    }


# ─── API: Dashboard Summary ────────────────────────────────

@app.get("/api/investigations/{inv_id}/summary", tags=["Dashboard"])
async def get_investigation_summary(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """Get a complete summary for the investigation dashboard."""
    inv = state.get_investigation(inv_id)
    if not inv:
        raise HTTPException(404, "Investigation not found")

    evidence_items = state.get_evidence_for_investigation(inv_id)
    findings = state.get_findings_for_investigation(inv_id)
    leads = state.get_leads_for_investigation(inv_id)
    documents = state.get_documents_for_investigation(inv_id)
    correlations = state.get_correlations_for_investigation(inv_id)
    timeline = state.get_timeline_for_investigation(inv_id)
    graph = get_graph_summary(inv_id)
    pipeline = state.pipeline_progress.get(inv_id)

    return {
        "investigation": inv,
        "counts": {
            "evidence": len(evidence_items),
            "findings": len(findings),
            "findings_pending": len([f for f in findings if f.status.value == "pending"]),
            "leads": len(leads),
            "leads_active": len([l for l in leads if l.status.value == "suggested"]),
            "documents": len(documents),
            "correlations": len(correlations),
            "timeline_events": len(timeline),
            "graph_nodes": graph["total_nodes"],
            "graph_edges": graph["total_edges"],
        },
        "pipeline": pipeline,
        "graph_summary": graph,
    }


# ─── API: SSE Events ────────────────────────────────────────

@app.get("/api/investigations/{inv_id}/events", tags=["Events"])
async def investigation_events(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
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
async def demo_pipeline(inv_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """
    DEMO ONLY: Generates plan, auto-approves, triggers background pipeline.
    In production, the investigator controls each step.
    """
    inv = state.get_investigation(inv_id)
    if not inv:
        raise HTTPException(404, "Investigation not found")

    state.log_audit(inv_id, "demo", "demo_pipeline_triggered",
                    "investigation", inv_id, "Demo mode: auto-generating and approving plan.")

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

    # Record in memory and transition states for demo
    memory = state.get_or_create_memory(inv_id)
    memory.record("human_decision", "demo",
                  "Demo mode: strategy auto-approved.")
    state.transition_state(inv_id, InvestigationState.RUNNING, "demo")

    asyncio.create_task(_execute_pipeline_background(inv_id))

    return {
        "message": "Execution engine started. Backbone analysis running in background.",
        "plan_id": plan.id,
        "state": "running",
        "track_progress": f"/api/investigations/{inv_id}/pipeline",
        "stream_events": f"/api/investigations/{inv_id}/events",
    }


# ─── Health Check ────────────────────────────────────────────

@app.get("/api/health", tags=["System"])
async def health():
    return {
        "status": "ok",
        "service": "AEGIS — Investigation Intelligence Platform",
        "architecture": "investigation_backbone",
        "registered_capabilities": len(CAPABILITY_REGISTRY),
        "capabilities": [
            "image_intelligence", "vehicle_intelligence", "open_source_intelligence",
            "document_intelligence", "audio_intelligence", "video_intelligence",
            "communication_services", "lead_intelligence", "correlation_engine",
            "discovery_engine",
        ],
        "backbone": {
            "planner": "active",
            "execution_engine": "active",
            "shared_context": "active",
            "discovery_engine": "active",
            "state_machine": "active",
        },
        "investigations": len(state.investigations),
        "evidence": len(state.evidence),
        "findings": len(state.findings),
        "leads": len(state.leads),
        "documents": len(state.draft_documents),
        "correlations": len(state.correlations),
        "discoveries": sum(len(c.discoveries) for c in state.investigation_contexts.values()),
        "graph_nodes": len(state.graph_nodes),
        "graph_edges": len(state.graph_edges),
        "audit_entries": len(state.audit_log),
    }


# ─── Static Files (Frontend) ─────────────────────────────────

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
