"""
WarehouseIQ — FastAPI Server
/upload/{file_key}  → structured data files (debriefs/safety/qc/returns)
/upload/voicememos  → audio files (mp3/wav/m4a/webm) — multiple at once
/upload/status      → check what's been uploaded

Run: uvicorn main:app --reload --port 8000
"""

import json, base64, threading
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pydantic import BaseModel
from graph import build_graph, initial_state
from agents.voice_agent import query_text, query_audio

app = FastAPI(title="WarehouseIQ — LangGraph", version="4.0")
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

GRAPH    = build_graph()
_status  = {"running":False,"step":None,"progress":0,"message":"","complete":False,"error":None}
_results = {}
_lock    = threading.Lock()

DATA_DIR  = Path("data")
VOICE_DIR = Path("data/voicememos")
DATA_DIR.mkdir(exist_ok=True)
VOICE_DIR.mkdir(exist_ok=True)

# Structured data files
EXPECTED_FILES = {
    "debriefs": "synthetic_debriefs_1000.json",
    "safety":   "amazon_warehouse_safety_logs.json",
    "qc":       "amazon_warehouse_qc_flags.csv",
    "returns":  "amazon_synthetic_returns.csv",
}

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".webm", ".flac", ".ogg", ".aac"}



# ── Voice Memo Upload ─────────────────

@app.post("/upload/voicememos")
async def upload_voice_memos(files: List[UploadFile] = File(...)):
    """
    Upload one or more audio files as voice memos.
    Accepted formats: .mp3 .wav .m4a .webm .flac .ogg .aac
    Files are saved to data/voicememos/ and transcribed during pipeline ingestion.
    """
    if not files:
        raise HTTPException(400, "No files provided")

    results = []
    for file in files:
        filename = file.filename or "audio"
        suffix   = Path(filename).suffix.lower()

        if suffix not in AUDIO_EXTENSIONS:
            results.append({
                "filename": filename,
                "status":   "rejected",
                "error":    f"Unsupported format '{suffix}'. Use: {sorted(AUDIO_EXTENSIONS)}",
            })
            continue

        contents = await file.read()
        if not contents:
            results.append({"filename": filename, "status": "rejected", "error": "Empty file"})
            continue

        target = VOICE_DIR / filename
        # If filename already exists, add a counter suffix
        counter = 1
        while target.exists():
            target = VOICE_DIR / f"{Path(filename).stem}_{counter}{suffix}"
            counter += 1

        target.write_bytes(contents)
        size_kb = round(len(contents) / 1024, 1)
        print(f"[Upload] voice memo → {target.name} ({size_kb} KB)")
        results.append({
            "filename": target.name,
            "status":   "uploaded",
            "size_kb":  size_kb,
        })

    accepted = [r for r in results if r["status"] == "uploaded"]
    return {
        "uploaded": len(accepted),
        "rejected": len(results) - len(accepted),
        "files":    results,
    }

# ── Structured File Upload ─────────────────────────────────────────────────────

@app.post("/upload/{file_key}")
async def upload_file(file_key: str, file: UploadFile = File(...)):
    """Upload one of the 4 structured data files. file_key: debriefs|safety|qc|returns"""
    if file_key not in EXPECTED_FILES:
        raise HTTPException(400, f"Unknown key '{file_key}'. Use: {list(EXPECTED_FILES.keys())}")
    contents = await file.read()
    if not contents:
        raise HTTPException(400, "Empty file")
    target = DATA_DIR / EXPECTED_FILES[file_key]
    if target.suffix == ".json":
        try: json.loads(contents)
        except Exception: raise HTTPException(400, "Not valid JSON")
    elif target.suffix == ".csv":
        if b"," not in contents[:1000]:
            raise HTTPException(400, "Doesn't look like a CSV")
    target.write_bytes(contents)
    size_kb = round(len(contents) / 1024, 1)
    print(f"[Upload] {file_key} → {target.name} ({size_kb} KB)")
    return {"status": "uploaded", "file_key": file_key,
            "filename": target.name, "size_kb": size_kb}


@app.delete("/upload/{file_key}")
def delete_upload(file_key: str):
    """Remove a structured data file so it can be re-uploaded."""
    if file_key not in EXPECTED_FILES:
        raise HTTPException(400, f"Unknown key '{file_key}'")
    path = DATA_DIR / EXPECTED_FILES[file_key]
    if path.exists():
        path.unlink()
    return {"status": "deleted", "file_key": file_key}


@app.delete("/upload/voicememos/{filename}")
def delete_voice_memo(filename: str):
    """Remove a specific voice memo file."""
    path = VOICE_DIR / filename
    if not path.exists():
        raise HTTPException(404, f"File not found: {filename}")
    path.unlink()
    # Also clear transcript cache so it gets re-generated
    cache = VOICE_DIR / "_transcripts.json"
    if cache.exists():
        cache.unlink()
    return {"status": "deleted", "filename": filename}


# ── Upload Status ──────────────────────────────────────────────────────────────

@app.get("/upload/status")
def upload_status():
    """Returns status of all 4 structured files + list of voice memos."""
    files = {}
    all_required_ready = True
    for key, filename in EXPECTED_FILES.items():
        path   = DATA_DIR / filename
        exists = path.exists()
        files[key] = {
            "filename": filename,
            "uploaded": exists,
            "size_kb":  round(path.stat().st_size / 1024, 1) if exists else 0,
        }
        if not exists:
            all_required_ready = False

    # Voice memos
    audio_files = [f for f in VOICE_DIR.iterdir()
                   if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS] \
                  if VOICE_DIR.exists() else []

    return {
        "files":     files,
        "all_ready": all_required_ready,          # only counts the 4 required files
        "voicememos": {
            "count":    len(audio_files),
            "files":    [{"filename": f.name,
                          "size_kb":  round(f.stat().st_size / 1024, 1)}
                         for f in audio_files],
        },
    }


# ── Pipeline ──────────────────────────────────────────────────────────────────

STEP_MESSAGES = {
    "ingestion":  "Ingestion Agent — loading 5 data sources",
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
        for event in GRAPH.stream(state, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name in ("__start__", "__end__"):
                    continue
                step = node_output.get("current_step", node_name)
                pct  = node_output.get("progress", _status["progress"])
                err  = node_output.get("error")
                with _lock:
                    _status.update(step=step, progress=pct,
                                   message=STEP_MESSAGES.get(step, step),
                                   error=err, running=not node_output.get("complete", False))

        final = GRAPH.invoke(state)
        with _lock:
            _results = {k: v for k, v in final.items() if k != "raw_records"}
            _results["records"] = final.get("enriched_records", [])[:200]
            _results["records_total"] = len(final.get("enriched_records", []))
            _status.update(running=False, complete=True, progress=100,
                           step="complete", message="Pipeline complete", error=None)
    except Exception as e:
        with _lock:
            _status.update(running=False, error=str(e), message=f"Error: {e}")
        print(f"[Pipeline] Error: {e}")


@app.post("/pipeline/run")
async def run_pipeline(bg: BackgroundTasks):
    if _status["running"]:
        raise HTTPException(409, "Pipeline already running")
    missing = [fn for key, fn in EXPECTED_FILES.items()
               if not (DATA_DIR / fn).exists()]
    if missing:
        raise HTTPException(404, f"Upload these files first: {missing}")
    bg.add_task(_run_pipeline)
    return {"status": "started"}


@app.get("/pipeline/status")
def pipeline_status():
    with _lock:
        return dict(_status)


# ── Results ───────────────────────────────────────────────────────────────────

@app.get("/results")
def results():
    if not _results: raise HTTPException(404, "No results yet")
    return _results

@app.get("/results/patterns")
def get_patterns():
    if not _results: raise HTTPException(404, "No results")
    return _results.get("patterns", [])

@app.get("/results/actions")
def get_actions():
    if not _results: raise HTTPException(404, "No results")
    return _results.get("action_items", [])

@app.get("/results/alerts")
def get_alerts():
    if not _results: raise HTTPException(404, "No results")
    return _results.get("alerts", [])

@app.get("/results/stats")
def get_stats():
    if not _results: raise HTTPException(404, "No results")
    return _results.get("stats", {})

@app.get("/results/records")
def get_records():
    if not _results: raise HTTPException(404, "No results")
    return _results.get("records", [])


# ── Query / Voice ─────────────────────────────────────────────────────────────

class QueryReq(BaseModel):
    question: str

@app.post("/query")
def query(req: QueryReq):
    if not _results: raise HTTPException(404, "No results yet")
    state = {
    **_results,
    "messages": []
    }
    result = query_text(req.question, state)
    return {"question": req.question, "answer": result["response_text"]}

@app.post("/voice/audio")
async def voice_audio(file: UploadFile = File(...)):
    if not _results: raise HTTPException(404, "No results yet")
    audio  = await file.read()
    result = query_audio(audio, _results)
    return {
        "transcript":    result.get("transcript", ""),
        "response_text": result.get("response_text", ""),
        "audio_b64":     base64.b64encode(result.get("audio_bytes") or b"").decode(),
        "model":         result.get("model", ""),
        "fallback":      result.get("fallback", False),
    }

@app.get("/health")
def health():
    return {
        "status":         "ok",
        "graph_compiled": GRAPH is not None,
        "voice_dir":      str(VOICE_DIR),
        "audio_formats":  sorted(AUDIO_EXTENSIONS),
    }