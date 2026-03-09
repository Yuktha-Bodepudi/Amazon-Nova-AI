"""
WarehouseIQ — Ingestion Agent Node
LangGraph node: reads all 4 data files, normalizes into unified schema,
writes raw_records + ingestion_summary to shared WarehouseState.
"""

import json, csv
from pathlib import Path
from collections import Counter
from langchain_core.messages import SystemMessage
from state import WarehouseState


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
    }


def _load_debriefs() -> list[dict]:
    SEV = {1:"low",2:"low",3:"medium",4:"high",5:"critical"}
    with open("data/synthetic_debriefs_1000.json") as f:
        raw = json.load(f)
    out = []
    for item in raw:
        issues  = item.get("issues", [])
        max_sev = max((i.get("severity",1) for i in issues), default=1)
        parts   = [item.get("summary","")]
        if issues:
            parts.append("Issues: " + "; ".join(
                f"[{i['category']} sev={i['severity']}] {i['description']}" for i in issues
            ))
        if item.get("staffing_notes"):
            parts.append(f"Staffing: {item['staffing_notes']}")
        if item.get("followups"):
            parts.append("Followups: " + "; ".join(item["followups"]))
        r = _empty()
        r.update({
            "id": item["report_id"], "source_type": "debrief",
            "date": item["date"], "zone": item["zone"], "shift": item["shift"],
            "text": " ".join(parts),
            "issues": issues, "actions_taken": item.get("actions_taken",[]),
            "followups": item.get("followups",[]),
            "staffing_notes": item.get("staffing_notes"),
            "equipment_ids": item.get("equipment_ids",[]),
            "severity": SEV.get(max_sev,"medium"),
            "tags": list({i["category"] for i in issues}),
        })
        out.append(r)
    return out


def _load_safety() -> list[dict]:
    SEV = {"Near Miss":"low","Minor":"low","Moderate":"medium","Severe":"high"}
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
            "severity": SEV.get(item["severity"],"medium"),
            "tags": [
                item["event_type"].lower().replace(" ","_").replace("/","_"),
                item["equipment_involved"].lower().replace(" ","_"),
                "injury" if inj else "near_miss",
            ],
        })
        out.append(r)
    return out


def _load_qc() -> list[dict]:
    SEV = {"Low":"low","Medium":"medium","High":"high"}
    out = []
    with open("data/amazon_warehouse_qc_flags.csv", newline="") as f:
        for row in csv.DictReader(f):
            checked   = int(row["quantity_checked"] or 0)
            defective = int(row["quantity_defective"] or 0)
            rate      = round(defective/checked*100,1) if checked else 0.0
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
                "severity": SEV.get(row["defect_severity"],"medium"),
                "tags": [row["defect_type"].lower().replace(" ","_"), row["category"].lower(),
                         "flagged" if flagged else "ok"],
            })
            out.append(r)
    return out


def _load_returns() -> list[dict]:
    DEFECT = {"Item damaged","Defective product","Wrong item received","Missing parts"}
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
                "tags": [reason.lower().replace(" ","_"), row["category"].lower(),
                         row["condition"].lower()],
            })
            out.append(r)
    return out


# ── LangGraph Node ─────────────────────────────────────────────────────────────

def ingestion_node(state: WarehouseState) -> dict:
    """
    LangGraph node function.
    Returns partial state update — only the keys this node owns.
    """
    print("\n[Ingestion Agent] Loading 4 data sources...")

    LOADERS = {
        "debriefs": ("data/synthetic_debriefs_1000.json",      _load_debriefs),
        "safety":   ("data/amazon_warehouse_safety_logs.json",  _load_safety),
        "qc":       ("data/amazon_warehouse_qc_flags.csv",      _load_qc),
        "returns":  ("data/amazon_synthetic_returns.csv",       _load_returns),
    }

    all_records = []
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
            "error": "No records loaded. Copy data files to backend/data/",
            "current_step": "ingestion",
            "progress": 0,
            "messages": [SystemMessage(content="Ingestion failed: no data files found.")],
        }

    summary = {
        "total":        len(all_records),
        "by_type":      dict(Counter(r["source_type"] for r in all_records)),
        "by_warehouse": dict(Counter(r["warehouse_id"] for r in all_records
                                     if r.get("warehouse_id")).most_common()),
        "by_severity":  dict(Counter(r["severity"] for r in all_records)),
    }

    print(f"[Ingestion Agent] ✓ {len(all_records):,} total records | "
          f"sources: {set(r['source_type'] for r in all_records)}")

    return {
        "raw_records":       all_records,
        "ingestion_summary": summary,
        "current_step":      "ingestion",
        "progress":          15,
        "error":             None,
        "messages":          [SystemMessage(
            content=f"Ingestion complete: {len(all_records):,} records loaded from 4 sources. "
                    f"Distribution: {summary['by_type']}"
        )],
    }