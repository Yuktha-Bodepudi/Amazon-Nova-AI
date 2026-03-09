"""
WarehouseIQ — FastAPI Server
Wraps the LangGraph pipeline behind REST endpoints.
Uses graph.stream() so the frontend gets real-time progress updates.

Run: uvicorn main:app --reload --port 8000
"""

import json, base64, threading
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from graph import build_graph, initial_state
from agents.voice_agent import query_text, query_audio

app = FastAPI(title="WarehouseIQ — LangGraph", version="4.0")
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ── Singleton graph (compiled once at startup) ─────────────────────────────────
GRAPH = build_graph()

# ── Runtime state ──────────────────────────────────────────────────────────────
_status  = {"running":False,"step":None,"progress":0,"message":"","complete":False,"error":None}
_results = {}          # last completed pipeline results
_lock    = threading.Lock()

REQUIRED_FILES = [
    "data/synthetic_debriefs_1000.json",
    "data/amazon_warehouse_safety_logs.json",
    "data/amazon_warehouse_qc_flags.csv",
    "data/amazon_synthetic_returns.csv",
]


# ── Pipeline ──────────────────────────────────────────────────────────────────

STEP_MESSAGES = {
    "ingestion":  "Ingestion Agent — loading 4 data sources",
    "analysis":   "Analysis Agent — Nova Lite enriching records",
    "root_cause": "Root Cause Agent — autonomous tool-calling investigation",
    "action":     "Action Agent — generating actions & reports",
    "voice":      "Voice Agent — loading Nova Sonic context",
    "complete":   "Pipeline complete",
    "error":      "Pipeline error",
}

def _run_pipeline():
    global _results
    with _lock:
        _status.update(running=True, step="starting", progress=0,
                       message="Initializing LangGraph pipeline...",
                       complete=False, error=None)
    try:
        state = initial_state()

        # graph.stream() yields partial state updates after each node
        for event in GRAPH.stream(state, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name in ("__start__","__end__"):
                    continue
                step    = node_output.get("current_step", node_name)
                pct     = node_output.get("progress", _status["progress"])
                msg     = STEP_MESSAGES.get(step, step)
                err     = node_output.get("error")

                with _lock:
                    _status.update(step=step, progress=pct, message=msg,
                                   error=err, running=not node_output.get("complete",False))

                print(f"[API] Node '{node_name}' → step={step} progress={pct}%")

        # Collect final state via invoke (stream gives us partial updates)
        final = GRAPH.invoke(state)
        with _lock:
            _results = {k: v for k, v in final.items() if k != "raw_records"}
            _results["records"] = final.get("enriched_records", [])[:200]
            _results["records_total"] = len(final.get("enriched_records",[]))
            _status.update(running=False, complete=True, progress=100,
                           step="complete", message="Pipeline complete", error=None)

        print("[API] ✓ Pipeline complete")

    except Exception as e:
        with _lock:
            _status.update(running=False, error=str(e), message=f"Error: {e}")
        print(f"[API] ✗ Pipeline error: {e}")


@app.post("/pipeline/run")
async def run_pipeline(bg: BackgroundTasks):
    if _status["running"]:
        raise HTTPException(409, "Pipeline already running")
    missing = [p for p in REQUIRED_FILES if not Path(p).exists()]
    if missing:
        raise HTTPException(404, f"Missing data files: {missing}. Copy them to backend/data/")
    bg.add_task(_run_pipeline)
    return {"status": "started", "message": "LangGraph pipeline starting..."}


@app.get("/pipeline/status")
def status():
    with _lock:
        return dict(_status)


# ── Results ───────────────────────────────────────────────────────────────────

@app.get("/results")
def results():
    if not _results: raise HTTPException(404, "No results yet. Run pipeline first.")
    return _results

@app.get("/results/patterns")
def patterns():
    if not _results: raise HTTPException(404, "No results")
    return _results.get("patterns", [])

@app.get("/results/actions")
def actions():
    if not _results: raise HTTPException(404, "No results")
    return _results.get("action_items", [])

@app.get("/results/alerts")
def alerts():
    if not _results: raise HTTPException(404, "No results")
    return _results.get("alerts", [])

@app.get("/results/stats")
def stats():
    if not _results: raise HTTPException(404, "No results")
    return _results.get("stats", {})

@app.get("/results/records")
def records():
    if not _results: raise HTTPException(404, "No results")
    return _results.get("records", [])

@app.get("/results/graph-state")
def graph_state():
    """Return the full LangGraph state (minus large records list) for debugging."""
    if not _results: raise HTTPException(404, "No results")
    return {k:v for k,v in _results.items() if k not in ("records","enriched_records","raw_records")}


# ── Query / Voice ─────────────────────────────────────────────────────────────

class QueryReq(BaseModel):
    question: str

@app.post("/query")
def query(req: QueryReq):
    if not _results: raise HTTPException(404, "No results yet")
    # Pass full state to voice agent for multi-turn context
    result = query_text(req.question, _results)
    return {"question": req.question, "answer": result["response_text"]}

@app.post("/voice/audio")
async def voice_audio(file: UploadFile = File(...)):
    if not _results: raise HTTPException(404, "No results yet")
    audio = await file.read()
    result = query_audio(audio, _results)
    return {
        "transcript":    result.get("transcript",""),
        "response_text": result.get("response_text",""),
        "audio_b64":     base64.b64encode(result.get("audio_bytes") or b"").decode(),
        "model":         result.get("model",""),
        "fallback":      result.get("fallback", False),
    }

@app.get("/health")
def health():
    return {"status": "ok", "graph_compiled": GRAPH is not None,
            "tools_available": 8, "models": ["nova-lite","nova-pro","nova-sonic"]}