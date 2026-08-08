# AEGIS v3 — Implementation Walkthrough

## What Was Built

AEGIS has been transformed from a basic PoC into a **full AI Investigation Workflow Engine** with 8 specialized agents running in parallel.

---

## Architecture

```
Evidence Upload
      │
      ▼
┌─────────────────────────────────────┐
│     PARALLEL AGENT EXECUTION        │
│                                     │
│  🔍 Vision Agent    🚗 Vehicle Agent │
│  📄 PDF Agent       🎤 Audio Agent  │
│  🎬 Video Agent     📋 Metadata     │
└─────────────┬───────────────────────┘
              │
              ▼
      🌐 OSINT Agent
      (Simulated Intelligence)
              │
              ▼
      🔗 Correlation Engine
      (Cross-evidence linking)
              │
              ▼
┌─────────────────────────────────────┐
│     PARALLEL SYNTHESIS              │
│                                     │
│  💡 Lead Generator  ✉️ Comms Agent  │
└─────────────────────────────────────┘
              │
              ▼
      📊 Investigation Dashboard
      (Real-time SSE updates)
```

---

## New Backend Files

### Agents
| File | Purpose |
|---|---|
| [vehicle_agent.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/vehicle_agent.py) | Vehicle forensics — make, model, color, registration plate, damage, modifications |
| [osint_agent.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/osint_agent.py) | Simulated OSINT intelligence using Gemini reasoning |
| [communication_agent.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/communication_agent.py) | Auto-drafts MVD emails, court orders, FIRs, BOLO notices, evidence logs |
| [lead_generator.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/lead_generator.py) | Proactive investigation leads — specific next actions for investigator |
| [correlation.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/correlation.py) | Cross-evidence entity resolution, chain detection, cluster finding |
| [pdf_agent.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/pdf_agent.py) | PDF text extraction + entity analysis (names, phones, IDs, addresses) |
| [audio_agent.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/audio_agent.py) | Audio transcription and keyword/entity extraction |
| [video_agent.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/video_agent.py) | Video scene analysis, movement tracking, key moment detection |

### Modified Files
| File | Changes |
|---|---|
| [main.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/main.py) | Complete rewrite — parallel pipeline, 30+ API endpoints, SSE, demo mode |
| [models.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/models.py) | Added 6 new enums, 8 new models (Lead, Document, Correlation, Vehicle, Audio, etc.) |
| [state.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/state.py) | Added stores for leads, documents, correlations + query helpers |
| [graph.py](file:///c:/Users/saura/OneDrive/Desktop/hackp/backend/graph.py) | Added 7 new relationship types, BFS path-finding, cluster detection |

### Frontend
| File | Description |
|---|---|
| [index.html](file:///c:/Users/saura/OneDrive/Desktop/hackp/aegis_landing/index.html) | Premium command-center dashboard with stats, agent fleet status, activity feed |
| [workspace.html](file:///c:/Users/saura/OneDrive/Desktop/hackp/aegis_landing/workspace.html) | 3-pane investigation workspace with drag-drop upload, real-time SSE pipeline progress, tabbed findings/leads/documents/correlations |

---

## API Endpoints (30+)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/investigations` | Create new investigation |
| GET | `/api/investigations` | List all investigations |
| GET | `/api/investigations/{id}` | Get investigation details |
| POST | `/api/investigations/{id}/evidence` | Upload evidence files |
| GET | `/api/investigations/{id}/evidence` | List evidence |
| POST | `/api/investigations/{id}/plan` | Generate AI investigation plan |
| POST | `/api/plans/{id}/approve` | Approve plan → triggers pipeline |
| POST | `/api/investigations/{id}/demo-pipeline` | **One-click demo** (auto plan + run) |
| GET | `/api/investigations/{id}/pipeline` | Pipeline progress status |
| GET | `/api/investigations/{id}/findings` | List AI findings |
| POST | `/api/findings/{id}/approve` | Approve a finding |
| POST | `/api/findings/{id}/reject` | Reject a finding |
| GET | `/api/investigations/{id}/leads` | List AI-generated leads |
| POST | `/api/leads/{id}/accept` | Accept a lead |
| POST | `/api/leads/{id}/dismiss` | Dismiss a lead |
| GET | `/api/investigations/{id}/documents` | List auto-drafted documents |
| GET | `/api/documents/{id}` | View full document content |
| GET | `/api/investigations/{id}/correlations` | Cross-evidence correlations |
| GET | `/api/investigations/{id}/graph` | Knowledge graph (nodes + edges) |
| GET | `/api/investigations/{id}/timeline` | Investigation timeline |
| POST | `/api/investigations/{id}/report` | Generate full report |
| GET | `/api/investigations/{id}/audit` | Complete audit trail |
| GET | `/api/investigations/{id}/summary` | Dashboard summary (all counts) |
| GET | `/api/investigations/{id}/events` | **SSE stream** (real-time updates) |
| GET | `/api/capabilities` | List registered capabilities |
| GET | `/api/health` | System health check |

---

## How to Test

### Quick Test Flow
1. Open **http://localhost:8000** in your browser
2. Click **"Start Investigation"**
3. Name it, set a goal (e.g., "Identify vehicle and persons in the incident")
4. Upload evidence images (crime scene photos, vehicle images, etc.)
5. Click **"Run All Agents"** in the workspace
6. Watch the pipeline progress bar in real-time via SSE
7. Review: Findings → Leads → Documents → Correlations tabs

### Server Startup
```
start.bat
```
Or manually:
```powershell
$env:GEMINI_API_KEY="your-key"; python -m uvicorn main:app --reload --port 8000
```

---

## Verification

- ✅ Server starts with all 8 capabilities and 9 agents
- ✅ Health check returns `ok` with full system status
- ✅ Dashboard renders with premium dark theme
- ✅ Workspace renders with 3-pane layout
- ✅ API docs available at `/docs`
