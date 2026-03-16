"""
WarehouseIQ — Ingestion Agent Node
LangGraph node: reads all 5 data sources, normalizes into unified schema.

Sources:
  1. synthetic_debriefs_1000.json      → source_type="debrief"
  2. amazon_warehouse_safety_logs.json → source_type="safety"
  3. amazon_warehouse_qc_flags.csv     → source_type="qc"
  4. amazon_synthetic_returns.csv      → source_type="returns"
  5. data/voicememos/*.{mp3,wav,m4a}   → source_type="voice"
     └─ AWS Transcribe (speech-to-text) + Nova Lite (structured extraction)
"""

import json, csv, uuid, time, boto3
from pathlib import Path
from collections import Counter
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from state import WarehouseState


# ── Shared empty record template ───────────────────────────────────────────────

def _empty() -> dict:
    return {
        "id": None, "source_type": None, "date": None,
        "warehouse_id": None, "zone": None, "shift": None,
        "text": None, "tags": [], "severity": None,
        # debrief
        "issues": [], "actions_taken": [], "followups": [],
        "staffing_notes": None, "equipment_ids": [],
        # safety
        "event_type": None, "area": None, "equipment_involved": None,
        "injury_reported": None, "days_lost": None, "reported_by": None,
        # qc
        "product_id": None, "category": None, "defect_type": None,
        "defect_severity": None, "quantity_checked": None,
        "quantity_defective": None, "defect_rate_pct": None,
        "qc_status": None, "flagged_for_review": None, "inspector_level": None,
        # returns
        "order_id": None, "price": None, "return_reason": None,
        "return_days": None, "condition": None,
        "customer_type": None, "resolution": None,
        # voice
        "audio_file": None, "transcript": None, "duration_seconds": None,
    }


# ── Source loaders ─────────────────────────────────────────────────────────────

def _load_debriefs() -> list[dict]:
    SEV = {1:"low", 2:"low", 3:"medium", 4:"high", 5:"critical"}
    with open("data/synthetic_debriefs_1000.json") as f:
        raw = json.load(f)
    out = []
    for item in raw:
        issues  = item.get("issues", [])
        max_sev = max((i.get("severity", 1) for i in issues), default=1)
        parts   = [item.get("summary", "")]
        if issues:
            parts.append("Issues: " + "; ".join(
                f"[{i['category']} sev={i['severity']}] {i['description']}" for i in issues))
        if item.get("staffing_notes"):
            parts.append(f"Staffing: {item['staffing_notes']}")
        if item.get("followups"):
            parts.append("Followups: " + "; ".join(item["followups"]))
        r = _empty()
        r.update({
            "id": item["report_id"], "source_type": "debrief",
            "date": item["date"], "zone": item["zone"], "shift": item["shift"],
            "text": " ".join(parts),
            "issues": issues, "actions_taken": item.get("actions_taken", []),
            "followups": item.get("followups", []),
            "staffing_notes": item.get("staffing_notes"),
            "equipment_ids": item.get("equipment_ids", []),
            "severity": SEV.get(max_sev, "medium"),
            "tags": list({i["category"] for i in issues}),
        })
        out.append(r)
    return out


def _load_safety() -> list[dict]:
    SEV = {"Near Miss": "low", "Minor": "low", "Moderate": "medium", "Severe": "high"}
    with open("data/amazon_warehouse_safety_logs.json") as f:
        raw = json.load(f)
    out = []
    for item in raw:
        inj  = item.get("injury_reported", False)
        days = item.get("days_lost", 0)
        r = _empty()
        r.update({
            "id": item["log_id"], "source_type": "safety",
            "date": item["timestamp"][:10], "warehouse_id": item["warehouse_id"],
            "shift": item["shift"],
            "text": (f"{item['event_type']} in {item['area']} "
                     f"involving {item['equipment_involved']}. "
                     f"Severity: {item['severity']}. "
                     + (f"Injury — {days} days lost. " if inj else "No injury. ")
                     + f"Reported by {item['reported_by']}."),
            "event_type": item["event_type"], "area": item["area"],
            "equipment_involved": item["equipment_involved"],
            "injury_reported": inj, "days_lost": days,
            "reported_by": item["reported_by"],
            "severity": SEV.get(item["severity"], "medium"),
            "tags": [
                item["event_type"].lower().replace(" ", "_").replace("/", "_"),
                item["equipment_involved"].lower().replace(" ", "_"),
                "injury" if inj else "near_miss",
            ],
        })
        out.append(r)
    return out


def _load_qc() -> list[dict]:
    SEV = {"Low": "low", "Medium": "medium", "High": "high"}
    out = []
    with open("data/amazon_warehouse_qc_flags.csv", newline="") as f:
        for row in csv.DictReader(f):
            checked   = int(row["quantity_checked"] or 0)
            defective = int(row["quantity_defective"] or 0)
            rate      = round(defective / checked * 100, 1) if checked else 0.0
            flagged   = row["flagged_for_review"] == "Yes"
            r = _empty()
            r.update({
                "id": row["qc_id"], "source_type": "qc",
                "date": row["inspection_date"], "warehouse_id": row["warehouse_id"],
                "product_id": row["product_id"], "category": row["category"],
                "text": (f"{row['defect_type']} ({row['defect_severity']}) on "
                         f"{row['category']} product {row['product_id']} at {row['warehouse_id']}. "
                         f"Defect rate {rate}% ({defective}/{checked}). "
                         f"{row['inspector_level']} inspector. {row['qc_status']}."
                         + (" FLAGGED." if flagged else "")),
                "defect_type": row["defect_type"], "defect_severity": row["defect_severity"],
                "quantity_checked": checked, "quantity_defective": defective,
                "defect_rate_pct": rate, "qc_status": row["qc_status"],
                "flagged_for_review": row["flagged_for_review"],
                "inspector_level": row["inspector_level"],
                "severity": SEV.get(row["defect_severity"], "medium"),
                "tags": [row["defect_type"].lower().replace(" ", "_"),
                         row["category"].lower(),
                         "flagged" if flagged else "ok"],
            })
            out.append(r)
    return out


def _load_returns() -> list[dict]:
    DEFECT = {"Item damaged", "Defective product", "Wrong item received", "Missing parts"}
    out = []
    with open("data/amazon_synthetic_returns.csv", newline="") as f:
        for row in csv.DictReader(f):
            reason = row["return_reason"]
            r = _empty()
            r.update({
                "id": row["order_id"], "source_type": "returns",
                "product_id": row["product_id"], "category": row["category"],
                "text": (f"Return: {row['category']} product {row['product_id']} "
                         f"(${float(row['price']):.2f}). Reason: {reason}. "
                         f"After {row['return_days']} days, {row['condition']} condition. "
                         f"{row['customer_type']} customer. Resolution: {row['resolution']}."),
                "price": float(row["price"]),
                "return_reason": reason, "return_days": int(row["return_days"]),
                "condition": row["condition"], "customer_type": row["customer_type"],
                "resolution": row["resolution"],
                "severity": "high" if reason in DEFECT else "low",
                "tags": [reason.lower().replace(" ", "_"),
                         row["category"].lower(), row["condition"].lower()],
            })
            out.append(r)
    return out


# ── Voice Memo Ingestion ───────────────────────────────────────────────────────

VOICE_EXTRACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a warehouse operations AI. Extract structured data from a voice memo transcript. "
     "Return ONLY valid JSON, no markdown.\n\n"
     "Known warehouses: WH-101, WH-203, WH-305, WH-410, WH-512\n"
     "Known zones: A1-A6, B1-B6, C1-C6, D1-D6\n"
     "Known shifts: day, night, Morning, Afternoon, Night\n"
     "Issue categories: safety, equipment, staffing, picking_errors\n"
     "Severity levels: low, medium, high, critical\n"
     "Safety areas: Receiving Dock, Packing Zone, Sorting Area, Loading Bay, Storage Aisle\n"
     "Event types: Object falling, Chemical spill, Overexertion, Electrical issue, "
     "Forklift collision, Slip/Fall, Equipment malfunction, Fire hazard"),
    ("human",
     "Transcript:\n\"\"\"{transcript}\"\"\"\n\n"
     "Return ONLY this JSON:\n"
     "{{\n"
     "  \"warehouse_id\": \"WH-xxx or null\",\n"
     "  \"zone\": \"zone code or null\",\n"
     "  \"shift\": \"day or night or null\",\n"
     "  \"date\": \"YYYY-MM-DD or null\",\n"
     "  \"severity\": \"low|medium|high|critical\",\n"
     "  \"summary\": \"one sentence summary of the memo\",\n"
     "  \"issues\": [\n"
     "    {{\"category\": \"safety|equipment|staffing|picking_errors\",\n"
     "      \"severity\": 1-5,\n"
     "      \"description\": \"what was reported\"}}\n"
     "  ],\n"
     "  \"actions_mentioned\": [\"list of actions mentioned\"],\n"
     "  \"followups\": [\"list of follow-up items mentioned\"],\n"
     "  \"tags\": [\"2-4 relevant tags\"]\n"
     "}}")
])


def _transcribe_audio(audio_path: Path) -> str:
    """
    Transcribe audio file using AWS Transcribe.
    Uploads to S3 temp bucket, starts transcription job, waits, returns transcript text.
    Falls back to filename-based placeholder if Transcribe is unavailable.
    """
    try:
        s3       = boto3.client("s3",           region_name="us-east-1")
        tc       = boto3.client("transcribe",   region_name="us-east-1")

        # Use a consistent bucket name derived from account ID
        sts         = boto3.client("sts")
        account_id  = sts.get_caller_identity()["Account"]
        bucket_name = f"warehouseiq-transcribe-{account_id}"

        # Create bucket if it doesn't exist
        try:
            s3.head_bucket(Bucket=bucket_name)
        except Exception:
            s3.create_bucket(Bucket=bucket_name)

        # Upload audio
        s3_key  = f"voicememos/{uuid.uuid4()}/{audio_path.name}"
        s3.upload_file(str(audio_path), bucket_name, s3_key)

        # Determine media format
        ext_map = {".mp3": "mp3", ".wav": "wav", ".m4a": "mp4",
                   ".webm": "webm", ".flac": "flac", ".ogg": "ogg"}
        media_format = ext_map.get(audio_path.suffix.lower(), "mp3")

        job_name = f"wiq-{uuid.uuid4().hex[:12]}"
        tc.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": f"s3://{bucket_name}/{s3_key}"},
            MediaFormat=media_format,
            LanguageCode="en-US",
        )

        # Poll until done (max 3 minutes)
        for _ in range(36):
            time.sleep(5)
            status = tc.get_transcription_job(TranscriptionJobName=job_name)
            state  = status["TranscriptionJob"]["TranscriptionJobStatus"]
            if state == "COMPLETED":
                uri = status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                import urllib.request
                with urllib.request.urlopen(uri) as resp:
                    result = json.loads(resp.read())
                transcript = result["results"]["transcripts"][0]["transcript"]
                # Cleanup
                s3.delete_object(Bucket=bucket_name, Key=s3_key)
                tc.delete_transcription_job(TranscriptionJobName=job_name)
                return transcript
            elif state == "FAILED":
                break

        return f"[Transcription failed for {audio_path.name}]"

    except Exception as e:
        print(f"  [Voice Ingestion] Transcribe unavailable ({e}), using filename as context")
        return f"[Voice memo from file: {audio_path.name}. Transcription unavailable.]"


def _load_voicememos() -> list[dict]:
    """
    Load all audio files from data/voicememos/.
    For each: transcribe → Nova Lite extraction → unified record.
    """
    memo_dir = Path("data/voicememos")
    if not memo_dir.exists():
        print("  [Voice] No voicememos directory found — skipping")
        return []

    audio_extensions = {".mp3", ".wav", ".m4a", ".webm", ".flac", ".ogg", ".aac"}
    audio_files = [f for f in memo_dir.iterdir()
                   if f.is_file() and f.suffix.lower() in audio_extensions]

    if not audio_files:
        print("  [Voice] No audio files found in data/voicememos/")
        return []

    print(f"  [Voice] Found {len(audio_files)} audio file(s) — transcribing...")

    llm   = ChatBedrockConverse(
        model="amazon.nova-lite-v1:0",
        region_name="us-east-1",
        max_tokens=600,
        temperature=0.1,
    )
    chain = VOICE_EXTRACT_PROMPT | llm | StrOutputParser()

    out = []
    for audio_path in audio_files:
        print(f"    → {audio_path.name}")
        try:
            # Step 1: transcribe
            transcript = _transcribe_audio(audio_path)
            print(f"      Transcript ({len(transcript)} chars): {transcript[:80]}...")

            # Step 2: extract structure via Nova Lite
            raw      = chain.invoke({"transcript": transcript[:2000]})
            extracted = json.loads(raw.replace("```json", "").replace("```", "").strip())

            # Step 3: build unified record
            r = _empty()
            r.update({
                "id":           f"VOICE-{uuid.uuid4().hex[:8].upper()}",
                "source_type":  "voice",
                "date":         extracted.get("date"),
                "warehouse_id": extracted.get("warehouse_id"),
                "zone":         extracted.get("zone"),
                "shift":        extracted.get("shift"),
                "severity":     extracted.get("severity", "medium"),
                "text":         (f"[Voice Memo] {extracted.get('summary', '')} "
                                 f"Transcript: {transcript[:300]}"),
                "transcript":   transcript,
                "audio_file":   audio_path.name,
                "issues":       extracted.get("issues", []),
                "actions_taken":extracted.get("actions_mentioned", []),
                "followups":    extracted.get("followups", []),
                "tags":         extracted.get("tags", []) + ["voice_memo"],
            })
            out.append(r)
            print(f"      Extracted: warehouse={r['warehouse_id']} zone={r['zone']} "
                  f"issues={len(r['issues'])}")

        except Exception as e:
            print(f"      Error processing {audio_path.name}: {e}")
            # Still add a record so the file is tracked
            r = _empty()
            r.update({
                "id":          f"VOICE-{uuid.uuid4().hex[:8].upper()}",
                "source_type": "voice",
                "severity":    "medium",
                "text":        f"[Voice Memo — processing error] {audio_path.name}: {e}",
                "audio_file":  audio_path.name,
                "tags":        ["voice_memo", "processing_error"],
            })
            out.append(r)

    return out


# ── LangGraph Node ─────────────────────────────────────────────────────────────

def ingestion_node(state: WarehouseState) -> dict:
    """
    LangGraph node: loads all 5 sources, returns unified records.
    Voice memos are optional — pipeline runs fine without them.
    """
    print("\n[Ingestion Agent] Loading data sources...")

    LOADERS = {
        "debriefs": ("data/synthetic_debriefs_1000.json",       _load_debriefs),
        "safety":   ("data/amazon_warehouse_safety_logs.json",   _load_safety),
        "qc":       ("data/amazon_warehouse_qc_flags.csv",       _load_qc),
        "returns":  ("data/amazon_synthetic_returns.csv",        _load_returns),
    }

    all_records = []

    # Load the 4 structured sources
    for name, (path, loader) in LOADERS.items():
        if not Path(path).exists():
            print(f"  ⚠  Missing: {path}")
            continue
        try:
            recs = loader()
            all_records.extend(recs)
            print(f"  ✓  {name}: {len(recs):,} records")
        except Exception as e:
            print(f"  ✗  {name}: {e}")

    if not all_records:
        return {
            "error":        "No records loaded — upload data files first",
            "current_step": "ingestion",
            "progress":     0,
            "messages":     [SystemMessage(content="Ingestion failed: no data files.")],
        }

    # Load voice memos (optional — won't fail pipeline if missing)
    voice_records = _load_voicememos()
    if voice_records:
        all_records.extend(voice_records)
        print(f"  ✓  voicememos: {len(voice_records)} records")
    else:
        print("  ℹ  voicememos: none uploaded (optional)")

    summary = {
        "total":        len(all_records),
        "by_type":      dict(Counter(r["source_type"] for r in all_records)),
        "by_warehouse": dict(Counter(r["warehouse_id"] for r in all_records
                                     if r.get("warehouse_id")).most_common()),
        "by_severity":  dict(Counter(r["severity"] for r in all_records
                                     if r.get("severity"))),
    }

    print(f"[Ingestion Agent] ✓ {len(all_records):,} total records | "
          f"sources: {summary['by_type']}")

    return {
        "raw_records":        all_records,
        "ingestion_summary":  summary,
        "current_step":       "ingestion",
        "progress":           15,
        "error":              None,
        "messages":           [SystemMessage(
            content=f"Ingestion complete: {len(all_records):,} records. "
                    f"Distribution: {summary['by_type']}"
        )],
    }