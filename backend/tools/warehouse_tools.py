"""
WarehouseIQ — LangChain Tools
These are @tool decorated functions that agents can call autonomously.
The Root Cause and Action agents use tool-calling to pull specific
data slices rather than being handed everything upfront.

This is what makes the system truly agentic — agents DECIDE which
tools to call based on the context, rather than following a fixed script.
"""

import json, csv
from pathlib import Path
from typing import Optional
from collections import Counter, defaultdict
from langchain_core.tools import tool


# ── Data loading tools ─────────────────────────────────────────────────────────

@tool
def load_shift_reports(zone: Optional[str] = None, shift: Optional[str] = None) -> str:
    """
    Load shift debrief reports from the warehouse.
    Optionally filter by zone (e.g. 'B2', 'C3') or shift ('day', 'night').
    Returns JSON array of matching reports with their issues.
    """
    path = Path("data/synthetic_debriefs_1000.json")
    if not path.exists():
        return json.dumps({"error": "File not found: data/synthetic_debriefs_1000.json"})

    with open(path) as f:
        data = json.load(f)

    if zone:
        data = [r for r in data if r.get("zone") == zone]
    if shift:
        data = [r for r in data if r.get("shift", "").lower() == shift.lower()]

    # Compact representation for token efficiency
    result = [{
        "report_id": r["report_id"],
        "date":  r["date"],
        "zone":  r["zone"],
        "shift": r["shift"],
        "summary": r["summary"],
        "issues":  r.get("issues", []),
        "staffing_notes": r.get("staffing_notes"),
    } for r in data[:50]]  # cap at 50 for context window

    return json.dumps({"count": len(data), "sample": result, "filter": {"zone": zone, "shift": shift}})


@tool
def load_safety_incidents(warehouse_id: Optional[str] = None,
                          severity: Optional[str] = None,
                          shift: Optional[str] = None) -> str:
    """
    Load safety incident logs from warehouses.
    Filter by warehouse_id (WH-101 to WH-512), severity (Near Miss/Minor/Moderate/Severe),
    or shift (Morning/Afternoon/Night).
    Returns incident counts and top patterns.
    """
    path = Path("data/amazon_warehouse_safety_logs.json")
    if not path.exists():
        return json.dumps({"error": "File not found"})

    with open(path) as f:
        data = json.load(f)

    if warehouse_id:
        data = [r for r in data if r.get("warehouse_id") == warehouse_id]
    if severity:
        data = [r for r in data if r.get("severity") == severity]
    if shift:
        data = [r for r in data if r.get("shift") == shift]

    injuries = [r for r in data if r.get("injury_reported")]
    result = {
        "filter": {"warehouse_id": warehouse_id, "severity": severity, "shift": shift},
        "total":         len(data),
        "injuries":      len(injuries),
        "total_days_lost": sum(r.get("days_lost", 0) for r in data),
        "by_event_type": dict(Counter(r["event_type"] for r in data).most_common(8)),
        "by_equipment":  dict(Counter(r["equipment_involved"] for r in data
                                      if r.get("equipment_involved") != "None").most_common(5)),
        "by_severity":   dict(Counter(r["severity"] for r in data).most_common()),
        "sample": [{
            "log_id":   r["log_id"],
            "date":     r["timestamp"][:10],
            "shift":    r["shift"],
            "event":    r["event_type"],
            "area":     r["area"],
            "equipment":r["equipment_involved"],
            "severity": r["severity"],
            "injured":  r["injury_reported"],
            "days_lost":r["days_lost"],
        } for r in data[:20]],
    }
    return json.dumps(result)


@tool
def load_qc_failures(warehouse_id: Optional[str] = None,
                     category: Optional[str] = None,
                     defect_type: Optional[str] = None) -> str:
    """
    Load QC inspection failures from warehouse quality control.
    Filter by warehouse_id (WH-101 to WH-512), product category
    (Electronics/Sports/Clothing/Home/Beauty), or defect_type
    (Wrong Item/Barcode Issue/Functional Failure/Cosmetic Defect/
     Missing Parts/Label Error/Packaging Damage).
    Returns failure rates and defect patterns.
    """
    path = Path("data/amazon_warehouse_qc_flags.csv")
    if not path.exists():
        return json.dumps({"error": "File not found"})

    with open(path, newline="") as f:
        data = list(csv.DictReader(f))

    if warehouse_id:
        data = [r for r in data if r["warehouse_id"] == warehouse_id]
    if category:
        data = [r for r in data if r["category"] == category]
    if defect_type:
        data = [r for r in data if r["defect_type"] == defect_type]

    failures = [r for r in data if r["qc_status"] == "Fail"]
    flagged  = [r for r in data if r["flagged_for_review"] == "Yes"]

    result = {
        "filter": {"warehouse_id": warehouse_id, "category": category, "defect_type": defect_type},
        "total":          len(data),
        "failures":       len(failures),
        "fail_rate_pct":  round(len(failures)/len(data)*100, 1) if data else 0,
        "flagged":        len(flagged),
        "by_defect_type": dict(Counter(r["defect_type"] for r in failures).most_common(7)),
        "by_category":    dict(Counter(r["category"]    for r in failures).most_common()),
        "by_warehouse":   dict(Counter(r["warehouse_id"] for r in failures).most_common()),
        "by_inspector":   dict(Counter(r["inspector_level"] for r in failures).most_common()),
        "sample": [{
            "qc_id":    r["qc_id"],
            "pid":      r["product_id"],
            "warehouse":r["warehouse_id"],
            "category": r["category"],
            "defect":   r["defect_type"],
            "severity": r["defect_severity"],
            "checked":  r["quantity_checked"],
            "defective":r["quantity_defective"],
            "status":   r["qc_status"],
            "flagged":  r["flagged_for_review"],
        } for r in failures[:20]],
    }
    return json.dumps(result)


@tool
def load_customer_returns(category: Optional[str] = None,
                          return_reason: Optional[str] = None,
                          customer_type: Optional[str] = None) -> str:
    """
    Load customer return records to identify product quality issues.
    Filter by category (Electronics/Sports/Clothing/Home/Beauty),
    return_reason (Item damaged/Defective product/Wrong item received/
    Missing parts/Quality not good/Not as described etc.),
    or customer_type (Prime/Non-Prime).
    Returns return rates and patterns.
    """
    path = Path("data/amazon_synthetic_returns.csv")
    if not path.exists():
        return json.dumps({"error": "File not found"})

    with open(path, newline="") as f:
        data = list(csv.DictReader(f))

    if category:
        data = [r for r in data if r["category"] == category]
    if return_reason:
        data = [r for r in data if r["return_reason"] == return_reason]
    if customer_type:
        data = [r for r in data if r["customer_type"] == customer_type]

    DEFECT = {"Item damaged","Defective product","Wrong item received","Missing parts"}
    defect_returns = [r for r in data if r["return_reason"] in DEFECT]

    result = {
        "filter": {"category": category, "return_reason": return_reason, "customer_type": customer_type},
        "total":               len(data),
        "defect_related":      len(defect_returns),
        "defect_rate_pct":     round(len(defect_returns)/len(data)*100, 1) if data else 0,
        "by_reason":           dict(Counter(r["return_reason"] for r in data).most_common()),
        "by_category":         dict(Counter(r["category"] for r in data).most_common()),
        "avg_return_days":     round(sum(int(r["return_days"]) for r in data)/len(data), 1) if data else 0,
        "by_condition":        dict(Counter(r["condition"] for r in data).most_common()),
        "by_resolution":       dict(Counter(r["resolution"] for r in data).most_common()),
    }
    return json.dumps(result)


# ── Cross-source analysis tools ────────────────────────────────────────────────

@tool
def find_product_overlap() -> str:
    """
    Find product IDs that appear in BOTH QC failures AND customer returns.
    This is the key cross-source signal: products that fail QC inspection
    and then get returned by customers, indicating a quality pipeline break.
    Returns the overlapping products grouped by category.
    """
    qc_path  = Path("data/amazon_warehouse_qc_flags.csv")
    ret_path = Path("data/amazon_synthetic_returns.csv")
    if not qc_path.exists() or not ret_path.exists():
        return json.dumps({"error": "Data files not found"})

    with open(qc_path, newline="") as f:
        qc = list(csv.DictReader(f))
    with open(ret_path, newline="") as f:
        returns = list(csv.DictReader(f))

    qc_fail_map  = {r["product_id"]: r for r in qc if r["qc_status"] == "Fail"}
    ret_map      = {r["product_id"]: r for r in returns}
    overlap_pids = set(qc_fail_map) & set(ret_map)

    by_cat: dict = defaultdict(list)
    for pid in overlap_pids:
        cat = qc_fail_map[pid].get("category", "?")
        by_cat[cat].append({
            "product_id":   pid,
            "defect_type":  qc_fail_map[pid]["defect_type"],
            "defect_sev":   qc_fail_map[pid]["defect_severity"],
            "warehouse":    qc_fail_map[pid]["warehouse_id"],
            "return_reason":ret_map[pid]["return_reason"],
            "return_days":  ret_map[pid]["return_days"],
        })

    return json.dumps({
        "total_overlap":  len(overlap_pids),
        "by_category":    {k: len(v) for k, v in by_cat.items()},
        "sample_by_cat":  {k: v[:4] for k, v in by_cat.items()},
        "insight": f"{len(overlap_pids)} products have BOTH a QC failure AND a customer return — direct quality pipeline break"
    })


@tool
def compare_shift_risk() -> str:
    """
    Compare safety risk and operational issues across shifts (Morning/Afternoon/Night).
    Correlates safety log injury rates with debrief issue severity by shift.
    Returns side-by-side comparison to identify which shift has highest risk.
    """
    s_path = Path("data/amazon_warehouse_safety_logs.json")
    d_path = Path("data/synthetic_debriefs_1000.json")
    if not s_path.exists():
        return json.dumps({"error": "Safety log not found"})

    with open(s_path) as f:
        safety = json.load(f)
    debriefs = []
    if d_path.exists():
        with open(d_path) as f:
            debriefs = json.load(f)

    result = {}
    for shift in ["Morning", "Afternoon", "Night"]:
        rs = [r for r in safety if r["shift"] == shift]
        inj = [r for r in rs if r["injury_reported"]]
        result[shift] = {
            "incidents":   len(rs),
            "injuries":    len(inj),
            "injury_rate": round(len(inj)/len(rs)*100, 1) if rs else 0,
            "days_lost":   sum(r["days_lost"] for r in rs),
            "severe":      sum(1 for r in rs if r["severity"] == "Severe"),
            "top_events":  dict(Counter(r["event_type"] for r in rs).most_common(3)),
            "top_equip":   dict(Counter(r["equipment_involved"] for r in rs
                                        if r["equipment_involved"] != "None").most_common(3)),
        }

    # Debrief comparison (day vs night only)
    for d_shift, s_shift in [("day","Morning"), ("night","Night")]:
        rd = [r for r in debriefs if r.get("shift") == d_shift]
        issues = [i for r in rd for i in r.get("issues", [])]
        result[s_shift]["debrief_reports"] = len(rd)
        result[s_shift]["debrief_issues"]  = len(issues)
        result[s_shift]["high_sev_issues"] = sum(1 for i in issues if i.get("severity",1) >= 4)
        result[s_shift]["picking_errors"]  = sum(1 for i in issues if i["category"] == "picking_errors")
        result[s_shift]["staffing_issues"] = sum(1 for i in issues if i["category"] == "staffing")

    return json.dumps(result)


@tool
def get_warehouse_scorecard(warehouse_id: str) -> str:
    """
    Get a comprehensive operational scorecard for a specific warehouse.
    Combines safety incidents, QC failures, and debrief issues.
    warehouse_id must be one of: WH-101, WH-203, WH-305, WH-410, WH-512
    Returns combined risk score and top issues for that warehouse.
    """
    s_path = Path("data/amazon_warehouse_safety_logs.json")
    q_path = Path("data/amazon_warehouse_qc_flags.csv")

    if not s_path.exists() or not q_path.exists():
        return json.dumps({"error": "Data files not found"})

    with open(s_path) as f:
        safety = json.load(f)
    with open(q_path, newline="") as f:
        qc = list(csv.DictReader(f))

    ws = [r for r in safety if r["warehouse_id"] == warehouse_id]
    wq = [r for r in qc    if r["warehouse_id"] == warehouse_id]
    wq_fail = [r for r in wq if r["qc_status"] == "Fail"]

    inj = [r for r in ws if r["injury_reported"]]
    # Simple risk score: weighted sum
    risk = len(inj)*3 + sum(r["days_lost"] for r in ws) + len(wq_fail)*2

    return json.dumps({
        "warehouse_id":   warehouse_id,
        "risk_score":     risk,
        "safety": {
            "total_incidents": len(ws),
            "injuries":        len(inj),
            "days_lost":       sum(r["days_lost"] for r in ws),
            "severe_events":   sum(1 for r in ws if r["severity"] == "Severe"),
            "top_events":      dict(Counter(r["event_type"] for r in ws).most_common(4)),
            "top_equipment":   dict(Counter(r["equipment_involved"] for r in ws
                                           if r["equipment_involved"] != "None").most_common(3)),
        },
        "qc": {
            "total":         len(wq),
            "failures":      len(wq_fail),
            "fail_rate_pct": round(len(wq_fail)/len(wq)*100, 1) if wq else 0,
            "flagged":       sum(1 for r in wq if r["flagged_for_review"] == "Yes"),
            "top_defects":   dict(Counter(r["defect_type"] for r in wq_fail).most_common(4)),
        },
    })


@tool
def get_category_quality_report(category: str) -> str:
    """
    Get a quality report for a product category linking QC failures to customer returns.
    category must be one of: Electronics, Sports, Clothing, Home, Beauty
    Shows QC fail rate AND customer defect return rate for the same category.
    """
    q_path = Path("data/amazon_warehouse_qc_flags.csv")
    r_path = Path("data/amazon_synthetic_returns.csv")

    with open(q_path, newline="") as f:
        qc = [r for r in csv.DictReader(f) if r["category"] == category]
    with open(r_path, newline="") as f:
        returns = [r for r in csv.DictReader(f) if r["category"] == category]

    DEFECT = {"Item damaged","Defective product","Wrong item received","Missing parts"}
    qc_fail   = [r for r in qc if r["qc_status"] == "Fail"]
    ret_defect = [r for r in returns if r["return_reason"] in DEFECT]

    return json.dumps({
        "category": category,
        "qc": {
            "total":      len(qc),
            "failures":   len(qc_fail),
            "fail_pct":   round(len(qc_fail)/len(qc)*100,1) if qc else 0,
            "top_defects":dict(Counter(r["defect_type"] for r in qc_fail).most_common(4)),
        },
        "returns": {
            "total":          len(returns),
            "defect_returns": len(ret_defect),
            "defect_pct":     round(len(ret_defect)/len(returns)*100,1) if returns else 0,
            "top_reasons":    dict(Counter(r["return_reason"] for r in returns).most_common(4)),
        },
        "insight": f"{category}: {round(len(qc_fail)/len(qc)*100,1) if qc else 0}% QC fail → {round(len(ret_defect)/len(returns)*100,1) if returns else 0}% defect returns"
    })


# ── Tool registry ──────────────────────────────────────────────────────────────

ALL_TOOLS = [
    load_shift_reports,
    load_safety_incidents,
    load_qc_failures,
    load_customer_returns,
    find_product_overlap,
    compare_shift_risk,
    get_warehouse_scorecard,
    get_category_quality_report,
]

TOOL_MAP = {t.name: t for t in ALL_TOOLS}