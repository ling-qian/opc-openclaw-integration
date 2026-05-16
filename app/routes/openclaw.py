"""
OpenClaw Integration API Routes
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.services.openclaw_service import openclaw_service

router = APIRouter(prefix="/openclaw", tags=["OpenClaw"])

class EventEmitRequest(BaseModel):
    type: str
    payload: Dict[str, Any]
    source: Optional[str] = "opc-platform"

class EventQueryRequest(BaseModel):
    type: Optional[str] = None
    source: Optional[str] = None
    after: Optional[str] = None  # ISO timestamp
    before: Optional[str] = None
    limit: int = 100
    offset: int = 0
    order: Optional[str] = "desc"

class AlgorithmRunRequest(BaseModel):
    prompt: str
    tier: Optional[str] = None  # E1-E5; if None, classifier decides
    work_dir: Optional[str] = None

@router.post("/event/emit")
async def emit_event(req: EventEmitRequest):
    """Emit an event into OpenClaw EventBus."""
    try:
        result = openclaw_service.emit_event(req.type, req.payload, req.source or "opc-platform")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/event/query")
async def query_events(req: EventQueryRequest):
    """Query past events with filters."""
    filters = req.dict(exclude_none=True)
    return openclaw_service.query_events(filters)

@router.get("/event/count")
async def count_events(type: Optional[str] = None, source: Optional[str] = None):
    """Count events matching filters."""
    filters = {}
    if type:
        filters['type'] = type
    if source:
        filters['source'] = source
    return {"count": openclaw_service.count_events(filters)}

@router.get("/event/groupBy")
async def group_events_by(field: str = "type", type: Optional[str] = None, source: Optional[str] = None):
    """Group counts by field."""
    filters = {}
    if type:
        filters['type'] = type
    if source:
        filters['source'] = source
    groups = openclaw_service.group_events_by(field, filters)
    return {"groups": groups}

@router.post("/algorithm/run")
async def run_algorithm(req: AlgorithmRunRequest):
    """Run Algorithm orchestrator for a given prompt."""
    try:
        result = openclaw_service.run_algorithm(req.prompt, tier=req.tier, work_dir=req.work_dir)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def status():
    """Health check for OpenClaw integration."""
    return {
        "service": "opc-openclaw-integration",
        "openclaw_workspace": openclaw_service.workspace,
        "event_history_exists": openclaw_service.event_history_dir.exists(),
        "algorithm_available": (openclaw_service.workspace / '.agents' / 'skills' / 'algorithm' / 'index.js').exists()
    }
