"""
WarehouseIQ — LangChain Tools

Evidence granularity is the core design principle of this file.
Every correlation function labels its evidence scope honestly:

  zone_local        — evidence matches at zone level (debriefs only)
  area_local        — evidence matches at warehouse + area (safety logs)
  warehouse_local   — evidence matches at warehouse level (QC, voice by warehouse)
  product_bridge    — returns linked via product_id → QC → warehouse_id
  global_supporting — evidence cannot be localized (debrief themes with no warehouse link)

Real linkage capability (audited from actual data):
  Safety:   warehouse_id + area  (25 clusters: 5 WH × 5 areas)
  Debriefs: zone only — NO warehouse_id. Cannot be warehouse-local.
  QC:       warehouse_id + category
  Returns:  product_id → QC product_id → warehouse_id (73 records linkable)
  Voice:    warehouse_id + zone when supervisor provides it

ALL_TOOLS and TOOL_MAP are defined at the BOTTOM of this file.
"""

import json
import csv
from pathlib import Path
from typing import Optional
from collections import Counter, defaultdict
from langchain_core.tools import tool


# ==============================================================================
# SECTION A: NORMALIZATION + HELPERS
# ==============================================================================

EQUIPMENT_SYNONYMS = {
    "conveyor belt": "Conveyor Belt",
    "conveyor":      "Conveyor Belt",
    "belt line":     "Conveyor Belt",
    "belt":          "Conveyor Belt",
    "forklift":      "Forklift",
    "lift truck":    "Forklift",
    "fork lift":     "Forklift",
    "pallet jack":   "Pallet Jack",
    "jack":          "Pallet Jack",
    "pallet":        "Pallet Jack",
    "scanner":       "Scanner",
    "rf scanner":    "Scanner",
    "handheld":      "Scanner",
    "rf gun":        "Scanner",
    "none":          None,
}

SHIFT_SYNONYMS = {
    "day":       "Day",
    "morning":   "Morning",
    "afternoon": "Afternoon",
    "night":     "Night",
}

ISSUE_THEME_KEYWORDS = {
    "equipment":       ["conveyor", "forklift", "pallet jack", "scanner", "malfunction",
                        "breakdown", "down", "stuck", "jam", "belt", "equipment"],
    "staffing":        ["short-staffed", "understaffed", "staffing", "coverage",
                        "headcount", "absentee", "overtime", "short staff"],
    "safety":          ["injury", "hazard", "spill", "fire", "slip", "fall",
                        "collision", "overexertion", "electrical", "chemical"],
    "picking_errors":  ["wrong item", "mispick", "picking error", "misroute",
                        "incorrect", "mis-sort", "mislabeled"],
    "congestion":      ["congestion", "bottleneck", "backup", "slow", "delay",
                        "backlog", "queue", "traffic", "blocked"],
    "temperature":     ["temperature", "cold", "heat", "humidity", "storage condition",
                        "spoil", "damage", "environment"],
    "manual_handling": ["manual", "rerouting", "manual reroute", "hand carry",
                        "workaround", "bypass"],
}

DEFECT_RETURN_REASONS = {
    "Item damaged", "Defective product", "Wrong item received", "Missing parts"
}


def normalize_equipment(text: str) -> Optional[str]:
    if not text:
        return None
    t = text.strip().lower()
    for key, canonical in EQUIPMENT_SYNONYMS.items():
        if key in t:
            return canonical
    return text.strip().title()


def normalize_shift(text: str) -> Optional[str]:
    if not text:
        return None
    return SHIFT_SYNONYMS.get(text.strip().lower(), text.strip().title())


def extract_equipment_mentions(text: str) -> list:
    if not text:
        return []
    t = text.lower()
    CANONICAL = {"Conveyor Belt", "Forklift", "Pallet Jack", "Scanner"}
    found = set()
    for key, canonical in EQUIPMENT_SYNONYMS.items():
        if canonical and canonical in CANONICAL and key in t:
            found.add(canonical)
    return sorted(found)


def extract_issue_themes(text: str) -> list:
    if not text:
        return []
    t = text.lower()
    return [theme for theme, kws in ISSUE_THEME_KEYWORDS.items() if any(k in t for k in kws)]


def safe_json_load(path: Path) -> Optional[list]:
    try:
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def safe_csv_load(path: Path) -> Optional[list]:
    try:
        if not path.exists():
            return None
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return None


# ==============================================================================
# SECTION B: INDIVIDUAL QUERY TOOLS (unchanged interface)
# ==============================================================================

@tool
def load_shift_reports(zone: Optional[str] = None, shift: Optional[str] = None) -> str:
    """
    Load shift debrief reports. Filter by zone (e.g. 'C3') or shift ('day'/'night').
    Note: debriefs have zone but NO warehouse_id — results are zone-local, not warehouse-local.
    """
    data = safe_json_load(Path("data/synthetic_debriefs_1000.json"))
    if data is None:
        return json.dumps({"error": "File not found"})
    if zone:
        data = [r for r in data if r.get("zone") == zone]
    if shift:
        data = [r for r in data
                if normalize_shift(r.get("shift","")) == normalize_shift(shift)]
    return json.dumps({
        "count": len(data),
        "scope_note": "Debriefs have zone but no warehouse_id — cannot filter by warehouse",
        "sample": [{
            "report_id": r["report_id"], "date": r["date"], "zone": r["zone"],
            "shift": r["shift"], "summary": r["summary"],
            "issues": r.get("issues", []), "staffing_notes": r.get("staffing_notes"),
            "equipment_ids": r.get("equipment_ids", []),
        } for r in data[:50]],
        "filter": {"zone": zone, "shift": shift},
    })


@tool
def load_safety_incidents(warehouse_id: Optional[str] = None,
                          severity: Optional[str] = None,
                          shift: Optional[str] = None,
                          event_type: Optional[str] = None) -> str:
    """
    Load safety incident logs. Filter by warehouse_id, severity, shift, or event_type.
    Safety logs have warehouse_id + area — most specific is (warehouse, area).
    Event types: Fire hazard / Forklift collision / Chemical spill / Slip/Fall /
    Overexertion / Object falling / Electrical issue / Equipment malfunction
    """
    data = safe_json_load(Path("data/amazon_warehouse_safety_logs.json"))
    if data is None:
        return json.dumps({"error": "File not found"})
    if warehouse_id:
        data = [r for r in data if r.get("warehouse_id") == warehouse_id]
    if severity:
        data = [r for r in data if r.get("severity") == severity]
    if shift:
        data = [r for r in data
                if normalize_shift(r.get("shift","")) == normalize_shift(shift)]
    if event_type:
        data = [r for r in data if r.get("event_type") == event_type]
    injuries = [r for r in data if r.get("injury_reported")]
    return json.dumps({
        "filter": {"warehouse_id": warehouse_id, "severity": severity,
                   "shift": shift, "event_type": event_type},
        "total": len(data), "injuries": len(injuries),
        "total_days_lost": sum(r.get("days_lost", 0) for r in data),
        "by_event_type": dict(Counter(r["event_type"] for r in data).most_common(8)),
        "by_area":       dict(Counter(r["area"]       for r in data).most_common()),
        "by_equipment":  dict(Counter(
            normalize_equipment(r["equipment_involved"])
            for r in data if r.get("equipment_involved") != "None"
        ).most_common(5)),
        "by_severity":   dict(Counter(r["severity"] for r in data).most_common()),
        "sample": [{
            "log_id":    r["log_id"], "date": r["timestamp"][:10],
            "shift":     r["shift"],  "event": r["event_type"],
            "area":      r["area"],
            "equipment": normalize_equipment(r["equipment_involved"]),
            "severity":  r["severity"],
            "injured":   r["injury_reported"], "days_lost": r["days_lost"],
        } for r in data[:20]],
    })


@tool
def load_qc_failures(warehouse_id: Optional[str] = None,
                     category: Optional[str] = None,
                     defect_type: Optional[str] = None) -> str:
    """
    Load QC inspection failures. Filter by warehouse_id, category, or defect_type.
    QC has warehouse_id + category — most specific is (warehouse, category) fail rate.
    """
    data = safe_csv_load(Path("data/amazon_warehouse_qc_flags.csv"))
    if data is None:
        return json.dumps({"error": "File not found"})
    if warehouse_id:
        data = [r for r in data if r["warehouse_id"] == warehouse_id]
    if category:
        data = [r for r in data if r["category"] == category]
    if defect_type:
        data = [r for r in data if r["defect_type"] == defect_type]
    failures = [r for r in data if r["qc_status"] == "Fail"]
    flagged  = [r for r in data if r["flagged_for_review"] == "Yes"]
    return json.dumps({
        "filter":       {"warehouse_id": warehouse_id, "category": category,
                         "defect_type": defect_type},
        "total":        len(data), "failures": len(failures),
        "fail_rate_pct": round(len(failures)/len(data)*100, 1) if data else 0,
        "flagged":      len(flagged),
        "by_defect_type": dict(Counter(r["defect_type"] for r in failures).most_common(7)),
        "by_category":    dict(Counter(r["category"]    for r in failures).most_common()),
        "by_warehouse":   dict(Counter(r["warehouse_id"] for r in failures).most_common()),
        "by_inspector":   dict(Counter(r["inspector_level"] for r in failures).most_common()),
        "sample": [{
            "qc_id": r["qc_id"], "pid": r["product_id"], "warehouse": r["warehouse_id"],
            "category": r["category"], "defect": r["defect_type"],
            "severity": r["defect_severity"], "status": r["qc_status"],
        } for r in failures[:20]],
    })


@tool
def load_customer_returns(category: Optional[str] = None,
                          return_reason: Optional[str] = None,
                          customer_type: Optional[str] = None) -> str:
    """
    Load customer return records. Returns have no warehouse_id directly.
    They can be linked to warehouses via product_id → QC records (see find_product_overlap).
    """
    data = safe_csv_load(Path("data/amazon_synthetic_returns.csv"))
    if data is None:
        return json.dumps({"error": "File not found"})
    if category:
        data = [r for r in data if r["category"] == category]
    if return_reason:
        data = [r for r in data if r["return_reason"] == return_reason]
    if customer_type:
        data = [r for r in data if r["customer_type"] == customer_type]
    defect_returns = [r for r in data if r["return_reason"] in DEFECT_RETURN_REASONS]
    return json.dumps({
        "filter":         {"category": category, "return_reason": return_reason,
                           "customer_type": customer_type},
        "scope_note":     "Returns have no warehouse_id — use find_product_overlap to link via QC",
        "total":          len(data), "defect_related": len(defect_returns),
        "defect_rate_pct": round(len(defect_returns)/len(data)*100, 1) if data else 0,
        "by_reason":     dict(Counter(r["return_reason"] for r in data).most_common()),
        "by_category":   dict(Counter(r["category"]     for r in data).most_common()),
        "avg_return_days": round(sum(int(r["return_days"]) for r in data)/len(data), 1) if data else 0,
        "by_condition":  dict(Counter(r["condition"]  for r in data).most_common()),
    })


@tool
def find_product_overlap() -> str:
    """
    Find products in BOTH QC failures AND customer returns.
    This is the ONLY way to link returns to warehouses (via product_id → QC.warehouse_id).
    Returns defect return counts per warehouse via the product bridge.
    """
    qc_data  = safe_csv_load(Path("data/amazon_warehouse_qc_flags.csv"))
    ret_data = safe_csv_load(Path("data/amazon_synthetic_returns.csv"))
    if qc_data is None or ret_data is None:
        return json.dumps({"error": "Data files not found"})
    qc_fail_map = {r["product_id"]: r for r in qc_data if r["qc_status"] == "Fail"}
    ret_map     = {r["product_id"]: r for r in ret_data}
    overlap     = set(qc_fail_map) & set(ret_map)

    # Group by warehouse (via product bridge) + return reason
    wh_defect: dict = defaultdict(lambda: defaultdict(int))
    wh_all:    dict = defaultdict(int)
    by_cat:    dict = defaultdict(list)
    for pid in overlap:
        wh  = qc_fail_map[pid]["warehouse_id"]
        cat = qc_fail_map[pid]["category"]
        reason = ret_map[pid]["return_reason"]
        wh_all[wh] += 1
        if reason in DEFECT_RETURN_REASONS:
            wh_defect[wh][cat] += 1
        by_cat[cat].append({
            "product_id":    pid,
            "defect_type":   qc_fail_map[pid]["defect_type"],
            "warehouse":     wh,
            "return_reason": reason,
            "return_days":   ret_map[pid]["return_days"],
        })

    return json.dumps({
        "total_overlap":           len(overlap),
        "by_category":             {k: len(v) for k, v in by_cat.items()},
        "defect_returns_per_wh":   {wh: dict(cats) for wh, cats in wh_defect.items()},
        "all_returns_per_wh":      dict(wh_all),
        "sample_by_cat":           {k: v[:3] for k, v in by_cat.items()},
        "scope_note": (
            "Returns linked to warehouse via product_id→QC bridge. "
            f"{len(overlap)} of ~1000 returns linkable this way."
        ),
    })


@tool
def compare_shift_risk() -> str:
    """
    Compare safety risk across Morning/Afternoon/Night shifts.
    Cross-references with debrief issue counts by shift (debrief evidence is global).
    """
    safety   = safe_json_load(Path("data/amazon_warehouse_safety_logs.json"))
    debriefs = safe_json_load(Path("data/synthetic_debriefs_1000.json"))
    if safety is None:
        return json.dumps({"error": "Safety log not found"})
    result = {}
    for shift in ["Morning", "Afternoon", "Night"]:
        rs  = [r for r in safety if r["shift"] == shift]
        inj = [r for r in rs if r["injury_reported"]]
        result[shift] = {
            "incidents":   len(rs),
            "injuries":    len(inj),
            "injury_rate": round(len(inj)/len(rs)*100, 1) if rs else 0,
            "days_lost":   sum(r["days_lost"] for r in rs),
            "severe":      sum(1 for r in rs if r["severity"] == "Severe"),
            "top_events":  dict(Counter(r["event_type"] for r in rs).most_common(3)),
            "top_areas":   dict(Counter(r["area"]       for r in rs).most_common(3)),
        }
    if debriefs:
        for d_shift, s_shift in [("day","Morning"),("night","Night")]:
            rd     = [r for r in debriefs if r.get("shift") == d_shift]
            issues = [i for r in rd for i in r.get("issues", [])]
            result[s_shift]["global_debrief_context"] = {
                "scope":          "global — debriefs have no warehouse_id",
                "reports":        len(rd),
                "picking_errors": sum(1 for i in issues if i["category"]=="picking_errors"),
                "staffing":       sum(1 for i in issues if i["category"]=="staffing"),
                "equipment":      sum(1 for i in issues if i["category"]=="equipment"),
            }
    return json.dumps(result)


@tool
def get_warehouse_scorecard(warehouse_id: str) -> str:
    """
    Comprehensive scorecard for a warehouse. Safety broken down by area.
    Most specific level: warehouse + area (no zone available in safety logs).
    """
    safety = safe_json_load(Path("data/amazon_warehouse_safety_logs.json"))
    qc     = safe_csv_load(Path("data/amazon_warehouse_qc_flags.csv"))
    if safety is None or qc is None:
        return json.dumps({"error": "Data files not found"})
    ws      = [r for r in safety if r["warehouse_id"] == warehouse_id]
    wq      = [r for r in qc    if r["warehouse_id"] == warehouse_id]
    wq_fail = [r for r in wq if r["qc_status"] == "Fail"]
    inj     = [r for r in ws if r["injury_reported"]]
    area_summary = {}
    for area in set(r["area"] for r in ws):
        ar  = [r for r in ws if r["area"] == area]
        ai  = [r for r in ar if r["injury_reported"]]
        top_event = Counter(r["event_type"] for r in ar).most_common(1)
        top_equip = Counter(
            normalize_equipment(r["equipment_involved"])
            for r in ar if r["equipment_involved"] != "None"
        ).most_common(1)
        area_summary[area] = {
            "incidents":     len(ar), "injuries": len(ai),
            "days_lost":     sum(r["days_lost"] for r in ai),
            "top_event":     top_event[0][0] if top_event else None,
            "top_equipment": top_equip[0][0] if top_equip else None,
        }
    return json.dumps({
        "warehouse_id": warehouse_id,
        "risk_score":   len(inj)*3 + sum(r["days_lost"] for r in ws) + len(wq_fail)*2,
        "safety": {
            "total": len(ws), "injuries": len(inj),
            "days_lost": sum(r["days_lost"] for r in ws),
            "severe":    sum(1 for r in ws if r["severity"] == "Severe"),
            "by_event":  dict(Counter(r["event_type"] for r in ws).most_common(5)),
            "by_area":   area_summary,
        },
        "qc": {
            "total":        len(wq), "failures": len(wq_fail),
            "fail_rate_pct": round(len(wq_fail)/len(wq)*100, 1) if wq else 0,
            "flagged":      sum(1 for r in wq if r["flagged_for_review"] == "Yes"),
            "top_defects":  dict(Counter(r["defect_type"] for r in wq_fail).most_common(4)),
            "by_category":  dict(Counter(r["category"] for r in wq_fail).most_common()),
        },
    })


@tool
def get_category_quality_report(category: str) -> str:
    """
    Quality report for a product category. Links QC failures to customer returns.
    Most specific level: warehouse + category for QC; global for returns.
    category: Electronics | Sports | Clothing | Home | Beauty
    """
    qc      = safe_csv_load(Path("data/amazon_warehouse_qc_flags.csv"))
    returns = safe_csv_load(Path("data/amazon_synthetic_returns.csv"))
    if qc is None or returns is None:
        return json.dumps({"error": "Data files not found"})
    qc_cat  = [r for r in qc      if r["category"] == category]
    ret_cat = [r for r in returns if r["category"] == category]
    qc_fail    = [r for r in qc_cat  if r["qc_status"] == "Fail"]
    ret_defect = [r for r in ret_cat if r["return_reason"] in DEFECT_RETURN_REASONS]
    return json.dumps({
        "category": category,
        "qc": {
            "total": len(qc_cat), "failures": len(qc_fail),
            "fail_pct":     round(len(qc_fail)/len(qc_cat)*100, 1) if qc_cat else 0,
            "top_defects":  dict(Counter(r["defect_type"] for r in qc_fail).most_common(4)),
            "by_warehouse": dict(Counter(r["warehouse_id"] for r in qc_fail).most_common()),
            "scope": "warehouse_local — QC has warehouse_id",
        },
        "returns": {
            "total": len(ret_cat), "defect_returns": len(ret_defect),
            "defect_pct":  round(len(ret_defect)/len(ret_cat)*100, 1) if ret_cat else 0,
            "top_reasons": dict(Counter(r["return_reason"] for r in ret_cat).most_common(4)),
            "scope": "global — returns have no warehouse_id",
        },
    })


@tool
def load_voice_memos(warehouse_id: Optional[str] = None,
                     zone: Optional[str] = None,
                     shift: Optional[str] = None) -> str:
    """
    Load transcribed voice memo records. Voice memos may have warehouse_id and/or zone
    if the supervisor provided them. Filter by any combination.
    """
    cache_path = Path("data/voicememos/_transcripts.json")
    if not cache_path.exists():
        return json.dumps({"count": 0, "memos": [],
                           "note": "No voice memos uploaded yet."})
    memos = safe_json_load(cache_path) or []
    if warehouse_id:
        memos = [m for m in memos if m.get("warehouse_id") == warehouse_id]
    if zone:
        memos = [m for m in memos if m.get("zone") == zone]
    if shift:
        memos = [m for m in memos
                 if normalize_shift(m.get("shift","")) == normalize_shift(shift)]
    all_issues = [i for m in memos for i in m.get("issues", [])]
    all_themes = []
    for m in memos:
        all_themes.extend(extract_issue_themes(m.get("transcript","") or ""))
    return json.dumps({
        "filter": {"warehouse_id": warehouse_id, "zone": zone, "shift": shift},
        "count":  len(memos),
        "issue_categories": dict(Counter(i["category"] for i in all_issues).most_common()),
        "issue_themes":     dict(Counter(all_themes).most_common()),
        "memos": [{
            "id":           m.get("id"),
            "audio_file":   m.get("audio_file"),
            "warehouse_id": m.get("warehouse_id"),
            "zone":         m.get("zone"),
            "shift":        m.get("shift"),
            "severity":     m.get("severity"),
            "summary":      (m.get("text") or "")[:150],
            "issues":       m.get("issues", []),
            "transcript":   (m.get("transcript") or "")[:200],
        } for m in memos],
    })


# ==============================================================================
# SECTION C: CORRELATION ENGINE — private helpers
# ==============================================================================

def _load_voice_memo_cache() -> list:
    return safe_json_load(Path("data/voicememos/_transcripts.json")) or []


def _build_returns_signal(qc: list, returns: list) -> dict:
    """
    Build returns signal linked to warehouses via product_id → QC bridge.

    Returns:
      per_warehouse: {WH-xxx: {category: defect_return_count}}
      category_defect_rates: {category: defect_pct}
      linked_count: how many returns were linkable
      scope: "product_bridge — returns linked via product_id→QC.warehouse_id"
    """
    pid_to_wh_cat = {
        r["product_id"]: (r["warehouse_id"], r["category"])
        for r in qc if r["qc_status"] == "Fail"
    }

    wh_defect: dict = defaultdict(lambda: defaultdict(int))
    wh_all:    dict = defaultdict(int)
    linked = 0
    for r in returns:
        if r["product_id"] in pid_to_wh_cat:
            wh, cat = pid_to_wh_cat[r["product_id"]]
            wh_all[wh] += 1
            linked += 1
            if r["return_reason"] in DEFECT_RETURN_REASONS:
                wh_defect[wh][cat] += 1

    # Global category defect rates (no warehouse filter — returns have no warehouse_id)
    cat_total:  dict = Counter(r["category"]      for r in returns)
    cat_defect: dict = Counter(r["category"]      for r in returns
                               if r["return_reason"] in DEFECT_RETURN_REASONS)
    cat_rates = {
        cat: round(cat_defect.get(cat, 0) / total * 100, 1)
        for cat, total in cat_total.items() if total > 0
    }

    return {
        "per_warehouse":       {wh: dict(cats) for wh, cats in wh_defect.items()},
        "all_returns_per_wh":  dict(wh_all),
        "category_defect_rates": cat_rates,
        "global_top_reasons":  dict(Counter(
            r["return_reason"] for r in returns
            if r["return_reason"] in DEFECT_RETURN_REASONS
        ).most_common()),
        "linked_count":        linked,
        "total_returns":       len(returns),
        "scope":               "product_bridge — returns linked via product_id→QC.warehouse_id",
    }


def _build_debrief_zone_index(debriefs: list) -> dict:
    """
    Build a zone-level index of debrief evidence.
    Debriefs have zone but NO warehouse_id.
    Returns: {zone: {equipment_issues, theme_counts, shift_breakdown, issue_descriptions}}
    Granularity label: zone_local (for zone-specific data), global_supporting (for zone aggregates).
    """
    index: dict = {}
    for r in debriefs:
        zone = r.get("zone", "?")
        if zone not in index:
            index[zone] = {
                "zone":              zone,
                "report_count":      0,
                "equipment_issues":  defaultdict(int),  # {equipment: count}
                "theme_counts":      defaultdict(int),  # {theme: count}
                "shift_breakdown":   defaultdict(int),
                "issue_descriptions": [],               # sample descriptions
                "high_sev_issues":   0,
                "scope":             "zone_local",      # honest label
            }
        z = index[zone]
        z["report_count"] += 1
        z["shift_breakdown"][r.get("shift","?")] += 1
        for issue in r.get("issues", []):
            desc = issue.get("description", "")
            for t in extract_issue_themes(desc):
                z["theme_counts"][t] += 1
            for eq in extract_equipment_mentions(desc):
                z["equipment_issues"][eq] += 1
            if issue.get("severity", 1) >= 3 and len(z["issue_descriptions"]) < 3:
                z["issue_descriptions"].append(desc[:100])
            if issue.get("severity", 1) >= 4:
                z["high_sev_issues"] += 1

    # Convert defaultdicts to dicts for serialization
    for zone, z in index.items():
        z["equipment_issues"] = dict(Counter(z["equipment_issues"]).most_common(5))
        z["theme_counts"]     = dict(Counter(z["theme_counts"]).most_common(6))
        z["shift_breakdown"]  = dict(z["shift_breakdown"])

    return index


def _build_voice_index(voice_memos: list) -> dict:
    """
    Build voice memo index keyed by (warehouse_id, zone) when both available,
    or (warehouse_id, None) when only warehouse is known.

    Returns: {key_str: {warehouse_id, zone, themes, equipment_mentions, count, snippets}}
    with granularity labels.
    """
    index: dict = {}
    for m in voice_memos:
        wh   = m.get("warehouse_id")
        zone = m.get("zone")
        if not wh:
            continue  # can't use voice memos with no warehouse

        key = f"{wh}|{zone}" if zone else f"{wh}|*"
        if key not in index:
            index[key] = {
                "warehouse_id": wh,
                "zone":         zone,
                "count":        0,
                "themes":       defaultdict(int),
                "equipment":    defaultdict(int),
                "snippets":     [],
                "scope":        "zone_local" if zone else "warehouse_local",
            }
        entry = index[key]
        entry["count"] += 1

        combined = (m.get("transcript","") or "") + " " + (m.get("text","") or "")
        for t in extract_issue_themes(combined):
            entry["themes"][t] += 1
        for eq in extract_equipment_mentions(combined):
            entry["equipment"][eq] += 1
        for issue in m.get("issues", []):
            for t in extract_issue_themes(issue.get("description","")):
                entry["themes"][t] += 1

        if m.get("text") and len(entry["snippets"]) < 2:
            entry["snippets"].append((m.get("text",""))[:80])

    for key, entry in index.items():
        entry["themes"]    = dict(Counter(entry["themes"]).most_common(5))
        entry["equipment"] = dict(Counter(entry["equipment"]).most_common(4))

    return index


def _build_qc_warehouse_cat_rates(qc: list) -> dict:
    """
    Compute QC fail rate per (warehouse, category).
    Granularity: warehouse_local (QC has warehouse_id + category).
    """
    bucket: dict = defaultdict(lambda: {"total": 0, "fail": 0, "defects": Counter()})
    for r in qc:
        key = (r["warehouse_id"], r["category"])
        bucket[key]["total"] += 1
        if r["qc_status"] == "Fail":
            bucket[key]["fail"] += 1
            bucket[key]["defects"][r["defect_type"]] += 1

    result = {}
    for (wh, cat), v in bucket.items():
        if v["total"] < 3:
            continue
        result[f"{wh}|{cat}"] = {
            "warehouse_id":  wh,
            "category":      cat,
            "total":         v["total"],
            "failures":      v["fail"],
            "fail_rate_pct": round(v["fail"]/v["total"]*100, 1),
            "top_defects":   dict(v["defects"].most_common(3)),
            "scope":         "warehouse_local",
        }
    return result


def _confidence_and_granularity(sources_matched: list, scope_levels: list) -> tuple:
    """
    Compute confidence and evidence_granularity from what actually matched.

    sources_matched: list of source names that contributed evidence
    scope_levels: list of scope labels for each piece of evidence
      e.g. ["area_local","zone_local","warehouse_local","global_supporting"]

    Returns: (confidence: float, granularity: str, confidence_reason: list[str])
    """
    n_sources = len(set(sources_matched))

    # Best scope available
    scope_priority = ["zone_local","area_local","warehouse_local",
                      "product_bridge","global_supporting"]
    best_scope = "global_supporting"
    for sp in scope_priority:
        if sp in scope_levels:
            best_scope = sp
            break

    scope_scores = {
        "zone_local":       0.35,
        "area_local":       0.25,
        "warehouse_local":  0.15,
        "product_bridge":   0.10,
        "global_supporting":0.0,
    }
    base = scope_scores.get(best_scope, 0.0)
    conf = min(0.96, 0.45 + base + n_sources * 0.10)

    # Granularity label
    if "zone_local" in scope_levels and n_sources >= 2:
        granularity = "zone_local"
    elif "area_local" in scope_levels and n_sources >= 2:
        granularity = "area_local"
    elif "warehouse_local" in scope_levels or "product_bridge" in scope_levels:
        granularity = "warehouse_local" if n_sources >= 2 else "mixed"
    else:
        granularity = "global_supporting"

    reasons = []
    if "area_local" in scope_levels:
        reasons.append(f"Safety evidence is area-local (warehouse+area match)")
    if "zone_local" in scope_levels:
        reasons.append("Debrief or voice evidence is zone-local")
    if "warehouse_local" in scope_levels:
        reasons.append("QC/voice evidence is warehouse-local")
    if "product_bridge" in scope_levels:
        reasons.append("Returns linked via product_id→QC bridge (warehouse-level)")
    if "global_supporting" in scope_levels:
        reasons.append("Some evidence is global only (debrief has no warehouse_id)")
    if n_sources >= 3:
        reasons.append(f"{n_sources} distinct sources corroborate")
    elif n_sources == 2:
        reasons.append("2 sources corroborate")

    return round(conf, 2), granularity, reasons


def _build_honest_hypothesis(wh: str, area: str, zone: Optional[str],
                              primary_issue: str, inj: int,
                              downstream: list, granularity: str) -> str:
    """
    Build hypothesis wording that matches evidence granularity.
    Does NOT claim zone-level specificity unless evidence is zone_local.
    """
    if granularity in ("zone_local",) and zone:
        location = f"{wh} {area} / zone {zone}"
    elif granularity == "area_local":
        location = f"{wh} {area}"
    elif granularity == "warehouse_local":
        location = f"{wh} (area: {area}, local safety evidence)"
    else:
        location = f"{wh} {area} (some supporting evidence is network-wide)"

    hyp = f"In {location}, {primary_issue} is associated with {inj} injuries in safety logs."
    if downstream:
        hyp += (
            " Supporting signals from other sources suggest downstream effects including: "
            + "; ".join(downstream) + "."
        )
    if granularity == "global_supporting":
        hyp += (
            " Note: debrief and returns evidence is network-wide and supports "
            "this pattern in context but cannot be confirmed as specific to this location."
        )
    return hyp


def _build_area_clusters(safety: list, qc: list,
                          debrief_zone_index: dict,
                          voice_index: dict,
                          returns_signal: dict,
                          warehouse_id: Optional[str] = None) -> list:
    """
    Build clusters keyed by (warehouse_id, area).
    Debrief evidence is kept SEPARATE as global_supporting_debrief_context.
    Voice evidence is attached at the most specific matching level.
    Returns evidence is attached via product bridge when available.
    """
    AREAS = ["Receiving Dock","Packing Zone","Sorting Area","Loading Bay","Storage Aisle"]
    WHS   = [warehouse_id] if warehouse_id else ["WH-101","WH-203","WH-305","WH-410","WH-512"]

    clusters = []
    for wh in WHS:
        ws = [r for r in safety if r["warehouse_id"] == wh]
        wq = [r for r in qc    if r["warehouse_id"] == wh]

        for area in AREAS:
            area_safety = [r for r in ws if r["area"] == area]
            if not area_safety:
                continue

            area_inj   = [r for r in area_safety if r["injury_reported"]]
            top_events = Counter(r["event_type"]                     for r in area_safety).most_common(4)
            top_equip  = Counter(
                normalize_equipment(r["equipment_involved"])
                for r in area_safety if r["equipment_involved"] != "None"
            ).most_common(3)
            shifts_hit = dict(Counter(r["shift"] for r in area_inj).most_common(3))

            # ── QC for this warehouse (warehouse_local) ────────────────────────
            wq_fail    = [r for r in wq if r["qc_status"] == "Fail"]
            qc_defects = dict(Counter(r["defect_type"] for r in wq_fail).most_common(3))
            qc_cats    = dict(Counter(r["category"]    for r in wq_fail).most_common(3))

            # ── Returns via product bridge (product_bridge) ────────────────────
            returns_for_wh = returns_signal.get("per_warehouse", {}).get(wh, {})

            # ── Debrief: zone-level index (cannot link to warehouse) ───────────
            # Find debrief zones that match equipment seen in THIS area
            area_equip_names = [e[0] for e in top_equip if e[0]]
            matching_debrief_zones = {}
            for zone, zdata in debrief_zone_index.items():
                # Match if zone has equipment issues for any equipment seen in this area
                zone_equip = zdata.get("equipment_issues", {})
                if any(eq in zone_equip for eq in area_equip_names):
                    matching_debrief_zones[zone] = {
                        "equipment_matches": {
                            eq: zone_equip[eq] for eq in area_equip_names if eq in zone_equip
                        },
                        "other_themes": zdata.get("theme_counts", {}),
                        "high_sev": zdata.get("high_sev_issues", 0),
                        "scope": "zone_local",
                        "note": f"Zone {zone} has matching equipment issues "
                                f"but zone→warehouse mapping is not available in source data",
                    }
            # Keep only top 3 matching zones to avoid noise
            matching_debrief_zones = dict(
                sorted(matching_debrief_zones.items(),
                       key=lambda x: sum(x[1]["equipment_matches"].values()),
                       reverse=True)[:3]
            )

            # ── Voice: warehouse-level (most common) or zone-level if available ─
            voice_warehouse_key = f"{wh}|*"
            voice_wh_data = voice_index.get(voice_warehouse_key)
            voice_zone_data = {}
            for key, vdata in voice_index.items():
                if vdata["warehouse_id"] == wh and vdata.get("zone"):
                    voice_zone_data[vdata["zone"]] = vdata

            clusters.append({
                "warehouse_id":      wh,
                "area":              area,
                "safety_incidents":  len(area_safety),
                "injuries":          len(area_inj),
                "severe":            sum(1 for r in area_safety if r["severity"]=="Severe"),
                "days_lost":         sum(r["days_lost"] for r in area_inj),
                "top_event_types":   [e[0] for e in top_events],
                "top_equipment":     [e[0] for e in top_equip if e[0]],
                "injuries_by_shift": shifts_hit,
                # QC — warehouse_local
                "qc_warehouse_local": {
                    "top_defects":    qc_defects,
                    "top_categories": qc_cats,
                    "total_failures": len(wq_fail),
                    "scope":          "warehouse_local",
                },
                # Returns — product_bridge
                "returns_product_bridge": {
                    "defect_returns_by_category": returns_for_wh,
                    "scope": "product_bridge",
                    "note":  "Returns linked via product_id→QC bridge only",
                },
                # Debrief — equipment-matching zones (zone_local but no warehouse link)
                "debrief_matching_zones": matching_debrief_zones,
                "global_supporting_debrief_context": {
                    "note": "Debrief records have no warehouse_id — "
                            "themes below are network-wide, not specific to this warehouse/area",
                    "scope": "global_supporting",
                    "themes": dict(Counter(
                        t for z in debrief_zone_index.values()
                        for t in z["theme_counts"]
                    ).most_common(4)),
                },
                # Voice — zone-local if available, else warehouse-level
                "voice_zone_local": {
                    z: {
                        "themes":    v["themes"],
                        "equipment": v["equipment"],
                        "count":     v["count"],
                        "snippets":  v["snippets"],
                        "scope":     "zone_local",
                    } for z, v in voice_zone_data.items()
                },
                "voice_warehouse_local": {
                    "themes":    voice_wh_data["themes"]    if voice_wh_data else {},
                    "equipment": voice_wh_data["equipment"] if voice_wh_data else {},
                    "count":     voice_wh_data["count"]     if voice_wh_data else 0,
                    "snippets":  voice_wh_data["snippets"]  if voice_wh_data else [],
                    "scope":     "warehouse_local",
                },
                "scope_summary": {
                    "safety":   f"area_local ({wh}/{area})",
                    "qc":       f"warehouse_local ({wh})",
                    "returns":  "product_bridge (via QC product_id)",
                    "debriefs": "global_supporting (no warehouse_id in debrief source)",
                    "voice":    (
                        f"zone_local for zones {list(voice_zone_data.keys())} + "
                        f"warehouse_local for {wh}"
                        if voice_zone_data else f"warehouse_local for {wh}"
                        if voice_wh_data else "none"
                    ),
                },
            })

    clusters.sort(key=lambda x: -x["injuries"])
    return clusters[:20]


def _build_candidate_root_causes(clusters: list,
                                  debrief_zone_index: dict,
                                  voice_index: dict,
                                  returns_signal: dict,
                                  shift_corr: dict,
                                  fire_analysis: dict,
                                  forklift_analysis: dict) -> list:
    """
    Build specific candidate root cause hypotheses.
    Each candidate carries evidence_granularity and confidence_reason
    based on ACTUAL evidence scope, not assumed locality.
    """
    candidates = []
    cid = 1

    # ── Equipment-area candidates ───────────────────────────────────────────────
    for cl in clusters:
        wh   = cl["warehouse_id"]
        area = cl["area"]
        inj  = cl["injuries"]
        if inj < 5:
            continue

        for eq in cl["top_equipment"]:
            if not eq:
                continue

            sources_hit  = ["safety"]
            scope_levels = ["area_local"]
            evidence     = [
                f"Safety logs (area_local): {inj} injuries in {wh} {area}; "
                f"top events: {cl['top_event_types'][:2]}; {eq} is top equipment involved",
            ]

            # QC — warehouse_local
            qc_data = cl["qc_warehouse_local"]
            if qc_data["top_defects"]:
                sources_hit.append("qc")
                scope_levels.append("warehouse_local")
                evidence.append(
                    f"QC (warehouse_local): {qc_data['total_failures']} failures at {wh}; "
                    f"top defects: {list(qc_data['top_defects'].keys())[:2]}"
                )

            # Returns — product bridge
            ret_data = cl["returns_product_bridge"]["defect_returns_by_category"]
            if ret_data:
                sources_hit.append("returns")
                scope_levels.append("product_bridge")
                total_defect_rets = sum(ret_data.values())
                evidence.append(
                    f"Returns (product_bridge): {total_defect_rets} defect returns "
                    f"linked to {wh} via QC product bridge; "
                    f"categories: {list(ret_data.keys())[:2]}"
                )

            # Debrief — matching zones (zone_local but no warehouse link)
            debrief_zones = cl["debrief_matching_zones"]
            if debrief_zones:
                top_zone = list(debrief_zones.keys())[0]
                zd       = debrief_zones[top_zone]
                match_ct = sum(zd["equipment_matches"].values())
                sources_hit.append("debrief")
                scope_levels.append("zone_local")  # zone is local, but no warehouse link
                evidence.append(
                    f"Debrief (zone_local, no warehouse link): zone {top_zone} has "
                    f"{match_ct} {eq} equipment issues "
                    f"— zone→warehouse mapping not available in data"
                )

            # Voice — zone first, then warehouse
            voice_zone = cl["voice_zone_local"]
            voice_wh   = cl["voice_warehouse_local"]
            if voice_zone:
                top_vz = list(voice_zone.keys())[0]
                vd     = voice_zone[top_vz]
                if eq in vd.get("equipment", {}):
                    sources_hit.append("voice_memo")
                    scope_levels.append("zone_local")
                    evidence.append(
                        f"Voice memo (zone_local): zone {top_vz} at {wh} mentions "
                        f"{eq} ({vd['equipment'][eq]} times); "
                        f"themes: {list(vd['themes'].keys())[:2]}"
                    )
            elif voice_wh and voice_wh.get("count", 0) > 0:
                if eq in voice_wh.get("equipment", {}):
                    sources_hit.append("voice_memo")
                    scope_levels.append("warehouse_local")
                    evidence.append(
                        f"Voice memo (warehouse_local): {wh} memos mention {eq}; "
                        f"themes: {list(voice_wh.get('themes',{}).keys())[:2]}"
                    )

            # Downstream effects
            downstream = []
            if "picking_errors" in cl["global_supporting_debrief_context"]["themes"]:
                downstream.append("picking errors (global debrief signal)")
            if "congestion" in cl["global_supporting_debrief_context"]["themes"]:
                downstream.append("congestion patterns (global debrief signal)")
            if ret_data:
                downstream.append(
                    f"defect returns in categories: {list(ret_data.keys())[:2]} (product bridge)"
                )

            conf, granularity, conf_reasons = _confidence_and_granularity(
                sources_hit, scope_levels
            )

            worst_shift = (
                max(cl["injuries_by_shift"], key=cl["injuries_by_shift"].get)
                if cl["injuries_by_shift"] else "All"
            )

            hypothesis = _build_honest_hypothesis(
                wh, area, None, f"{eq} disruption",
                inj, downstream, granularity
            )

            candidates.append({
                "candidate_id":       f"CRC-{cid:03d}",
                "warehouse_id":       wh,
                "area":               area,
                "zone":               None,
                "shift":              worst_shift,
                "primary_issue":      f"{eq} disruption",
                "pattern_type":       "equipment_safety_quality",
                "sources":            list(set(sources_hit)),
                "evidence":           evidence,
                "hypothesis":         hypothesis,
                "confidence":         conf,
                "evidence_granularity": granularity,
                "confidence_reason":  conf_reasons,
                "action_hint": (
                    f"Inspect and service {eq} in {wh} {area}. "
                    f"Focus on {cl['top_event_types'][0] if cl['top_event_types'] else 'incidents'} "
                    f"during {worst_shift} shift."
                ),
            })
            cid += 1

    # ── Returns-linked quality candidates ──────────────────────────────────────
    # For warehouses where returns signal via product bridge is strong
    for wh, cat_counts in returns_signal.get("per_warehouse", {}).items():
        if not cat_counts:
            continue
        top_cat = max(cat_counts, key=cat_counts.get)
        ct      = cat_counts[top_cat]
        if ct < 2:
            continue

        # Find QC fail rate for this warehouse + category
        # Already computed — look for it in the rate data
        evidence = [
            f"Returns (product_bridge): {ct} defect returns linked to {wh} "
            f"via QC product bridge; top category: {top_cat}",
            f"Global return reasons (global): defect returns include "
            f"{list(returns_signal.get('global_top_reasons', {}).keys())[:2]}",
        ]
        sources_hit  = ["returns", "qc"]
        scope_levels = ["product_bridge", "warehouse_local"]

        # Check voice for handling/temperature themes at this warehouse
        voice_wh_key = f"{wh}|*"
        vd = voice_index.get(voice_wh_key, {})
        if vd and any(t in vd.get("themes", {}) for t in ["temperature","manual_handling"]):
            sources_hit.append("voice_memo")
            scope_levels.append("warehouse_local")
            matching_themes = [t for t in ["temperature","manual_handling"]
                               if t in vd.get("themes", {})]
            evidence.append(
                f"Voice memo (warehouse_local): {wh} memos mention "
                f"{matching_themes} — suggests handling or storage condition issues"
            )

        conf, granularity, conf_reasons = _confidence_and_granularity(
            sources_hit, scope_levels
        )

        candidates.append({
            "candidate_id":       f"CRC-{cid:03d}",
            "warehouse_id":       wh,
            "area":               None,
            "zone":               None,
            "shift":              "All",
            "primary_issue":      f"{top_cat} product defect returns",
            "pattern_type":       "qc_returns_quality_pipeline",
            "sources":            list(set(sources_hit)),
            "evidence":           evidence,
            "hypothesis": (
                f"At {wh}, {ct} defect returns are linked via product_id to QC failures "
                f"in the {top_cat} category. This suggests a quality pipeline failure "
                f"where products that fail QC inspection are still reaching customers. "
                + ("Voice memos at this warehouse suggest handling or storage condition "
                   "issues that may contribute."
                   if "voice_memo" in sources_hit else "")
                + " Note: returns cannot be directly localized to a specific area "
                  "within the warehouse without additional data."
            ),
            "confidence":         conf,
            "evidence_granularity": granularity,
            "confidence_reason":  conf_reasons,
            "action_hint": (
                f"Audit {top_cat} QC inspection process at {wh}. "
                f"Verify that failed items are quarantined and not shipped."
            ),
        })
        cid += 1

    # ── Fire hazard candidate ───────────────────────────────────────────────────
    if fire_analysis.get("total_fires", 0) > 10:
        fa       = fire_analysis
        top_area = max(fa.get("by_area", {}).items(), key=lambda x: x[1], default=("?", 0))
        top_wh   = max(fa.get("by_warehouse", {}).items(), key=lambda x: x[1], default=("?", 0))
        top_eq   = list(fa.get("by_equipment", {}).keys())[:2]

        # Check for voice/debrief support at this warehouse
        voice_wh_key = f"{top_wh[0]}|*"
        vd = voice_index.get(voice_wh_key, {})
        sources_hit  = ["safety"]
        scope_levels = ["area_local"]
        evidence_list = [
            f"Safety (area_local): {fa['total_fires']} fire hazards network-wide; "
            f"{fa['fire_injuries']} injuries; {fa['fire_days_lost']} days lost",
            f"Highest area: {top_area[0]} ({top_area[1]} fires); "
            f"equipment most involved: {', '.join(top_eq)}",
            f"Worst warehouse: {top_wh[0]} ({top_wh[1]} fires)",
        ]
        if vd and "safety" in vd.get("themes", {}):
            sources_hit.append("voice_memo")
            scope_levels.append("warehouse_local")
            evidence_list.append(
                f"Voice memo (warehouse_local): {top_wh[0]} memos mention safety themes"
            )

        conf, granularity, conf_reasons = _confidence_and_granularity(
            sources_hit, scope_levels
        )

        candidates.append({
            "candidate_id":       f"CRC-{cid:03d}",
            "warehouse_id":       top_wh[0],
            "area":               top_area[0],
            "zone":               None,
            "shift":              (list(fa.get("by_shift",{}).keys())[0]
                                   if fa.get("by_shift") else "All"),
            "primary_issue":      "Fire hazard concentration",
            "pattern_type":       "safety_event_cluster",
            "sources":            list(set(sources_hit)),
            "evidence":           evidence_list,
            "hypothesis": (
                f"Fire hazards are concentrated in {top_area[0]} at {top_wh[0]}, "
                f"primarily involving {', '.join(top_eq)}. "
                f"{fa['total_fires']} fire events with {fa['fire_days_lost']} days lost "
                "indicate a systemic ignition/equipment hazard, not isolated incidents."
            ),
            "confidence":         conf,
            "evidence_granularity": granularity,
            "confidence_reason":  conf_reasons,
            "action_hint": (
                f"Fire risk audit in {top_wh[0]} {top_area[0]}. "
                f"Inspect {', '.join(top_eq)} for ignition sources."
            ),
        })
        cid += 1

    # ── Forklift → conveyor causal chain candidate ─────────────────────────────
    if forklift_analysis.get("total_collisions", 0) > 10:
        fk       = forklift_analysis
        top_area = max(fk.get("by_area", {}).items(), key=lambda x: x[1], default=("?", 0))
        top_wh   = max(fk.get("by_warehouse", {}).items(), key=lambda x: x[1], default=("?", 0))
        conv_ct  = fk.get("conveyor_debrief_issues_network", 0)
        conv_zones = fk.get("conveyor_affected_zones", [])

        sources_hit  = ["safety"]
        scope_levels = ["area_local"]
        evidence_list = [
            f"Safety (area_local): {fk['total_collisions']} forklift collisions; "
            f"{fk['injuries']} injuries, {fk['days_lost']} days lost; "
            f"highest area: {top_area[0]} ({top_area[1]} collisions) at {top_wh[0]}",
        ]
        if conv_ct > 0:
            sources_hit.append("debrief")
            scope_levels.append("zone_local")  # debrief evidence is zone-local
            evidence_list.append(
                f"Debrief (zone_local, no warehouse link): {conv_ct} conveyor belt "
                f"equipment issues across zones {conv_zones[:5]} "
                "— zone→warehouse mapping not available but pattern corroborates collision→conveyor chain"
            )

        conf, granularity, conf_reasons = _confidence_and_granularity(
            sources_hit, scope_levels
        )

        candidates.append({
            "candidate_id":       f"CRC-{cid:03d}",
            "warehouse_id":       top_wh[0],
            "area":               top_area[0],
            "zone":               None,
            "shift":              (list(fk.get("by_shift",{}).keys())[0]
                                   if fk.get("by_shift") else "All"),
            "primary_issue":      "Forklift collision → conveyor disruption causal chain",
            "pattern_type":       "causal_chain_equipment_operational",
            "sources":            list(set(sources_hit)),
            "evidence":           evidence_list,
            "hypothesis": (
                f"Forklift collisions are concentrated in {top_area[0]} at {top_wh[0]} "
                f"({top_area[1]} of {fk['total_collisions']} network collisions). "
                + (f"Network-wide debrief data shows {conv_ct} conveyor belt equipment issues "
                   f"across {len(conv_zones)} zones. While zone→warehouse mapping is unavailable, "
                   "the co-occurrence of high forklift collisions and conveyor issues "
                   "supports a causal chain: collision → conveyor damage → operational disruption."
                   if conv_ct > 0 else "")
            ),
            "confidence":         conf,
            "evidence_granularity": granularity,
            "confidence_reason":  conf_reasons,
            "action_hint": (
                f"Install forklift speed limiters in {top_area[0]} at {top_wh[0]}. "
                "Add conveyor inspection after every forklift incident."
            ),
        })
        cid += 1

    # ── Night shift cross-source candidate ─────────────────────────────────────
    night   = shift_corr.get("Night", {})
    morning = shift_corr.get("Morning", {})
    night_deb   = night.get("global_debrief_context", {})
    morning_deb = morning.get("global_debrief_context", {})

    if night.get("injuries", 0) > 0:
        sources_hit  = ["safety"]
        scope_levels = ["area_local"]
        evidence_list = [
            f"Safety (area_local): Night shift: {night['injuries']} injuries, "
            f"{night.get('injury_rate',0)}% injury rate, {night.get('days_lost',0)} days lost",
            f"Safety: Morning comparison: {morning.get('injuries',0)} injuries",
        ]
        if night_deb:
            sources_hit.append("debrief")
            scope_levels.append("global_supporting")
            evidence_list.append(
                f"Debrief (global_supporting): night-shift debriefs: "
                f"{night_deb.get('picking_errors',0)} picking errors, "
                f"{night_deb.get('staffing',0)} staffing issues "
                "— network-wide, not warehouse-specific"
            )

        conf, granularity, conf_reasons = _confidence_and_granularity(
            sources_hit, scope_levels
        )

        candidates.append({
            "candidate_id":       f"CRC-{cid:03d}",
            "warehouse_id":       "ALL",
            "area":               "All Areas",
            "zone":               None,
            "shift":              "Night",
            "primary_issue":      "Night shift: elevated injuries + picking errors",
            "pattern_type":       "shift_cross_source",
            "sources":            list(set(sources_hit)),
            "evidence":           evidence_list,
            "hypothesis": (
                f"Night shift shows {night['injuries']} injuries "
                f"({night.get('injury_rate',0)}% injury rate) across all warehouses. "
                + (f"Global debrief data shows {night_deb.get('picking_errors',0)} picking "
                   f"errors and {night_deb.get('staffing',0)} staffing issues on night shift, "
                   "though this evidence cannot be localized to specific warehouses."
                   if night_deb else "")
                + " The dual safety+quality signal suggests reduced supervision at night "
                "drives both worker risk and operational errors."
            ),
            "confidence":         conf,
            "evidence_granularity": granularity,
            "confidence_reason":  conf_reasons,
            "action_hint": (
                "Increase supervisor coverage on night shift. "
                "Implement night-specific safety briefings and picking error tracking."
            ),
        })
        cid += 1

    return candidates[:14]


# ==============================================================================
# SECTION D: MAIN CORRELATION TOOL
# ==============================================================================

@tool
def correlate_across_sources(warehouse_id: Optional[str] = None) -> str:
    """
    PRIMARY INVESTIGATION TOOL — call this first, programmatically enforced.

    Performs honest cross-source correlation. Every piece of evidence is labeled
    with its actual scope:
      area_local         — safety logs (warehouse + area)
      warehouse_local    — QC (warehouse + category), voice (warehouse level)
      zone_local         — debriefs, voice (zone level, no warehouse link for debriefs)
      product_bridge     — returns linked via product_id → QC → warehouse_id
      global_supporting  — debrief themes without warehouse context

    Key insight: debriefs have zone but NO warehouse_id.
    They can NEVER be claimed as warehouse-local evidence.
    Returns can only be linked to warehouses via the product_id → QC bridge.

    Returns candidate_root_causes with evidence_granularity and confidence_reason
    fields on each candidate. Use these as the foundation for final pattern generation.
    """
    safety   = safe_json_load(Path("data/amazon_warehouse_safety_logs.json")) or []
    debriefs = safe_json_load(Path("data/synthetic_debriefs_1000.json")) or []
    qc       = safe_csv_load(Path("data/amazon_warehouse_qc_flags.csv"))   or []
    returns  = safe_csv_load(Path("data/amazon_synthetic_returns.csv"))    or []
    voice    = _load_voice_memo_cache()

    s_filt = [r for r in safety if r["warehouse_id"] == warehouse_id] if warehouse_id else safety
    q_filt = [r for r in qc    if r["warehouse_id"] == warehouse_id] if warehouse_id else qc

    # ── Pre-built indexes ───────────────────────────────────────────────────────
    debrief_zone_index = _build_debrief_zone_index(debriefs)
    voice_index        = _build_voice_index(voice)
    returns_signal     = _build_returns_signal(qc, returns)

    # ── Warehouse scorecards ────────────────────────────────────────────────────
    wh_scores = {}
    for wh in ["WH-101","WH-203","WH-305","WH-410","WH-512"]:
        if warehouse_id and wh != warehouse_id:
            continue
        ws  = [r for r in safety if r["warehouse_id"] == wh]
        wq  = [r for r in qc    if r["warehouse_id"] == wh]
        inj = [r for r in ws if r["injury_reported"]]
        wq_fail = [r for r in wq if r["qc_status"] == "Fail"]
        wh_scores[wh] = {
            "injuries":     len(inj),
            "days_lost":    sum(r["days_lost"] for r in ws),
            "severe":       sum(1 for r in ws if r["severity"] == "Severe"),
            "qc_failures":  len(wq_fail),
            "qc_fail_rate": round(len(wq_fail)/len(wq)*100, 1) if wq else 0,
            "top_events":   dict(Counter(r["event_type"] for r in ws).most_common(4)),
            "top_areas":    dict(Counter(r["area"] for r in inj).most_common(3)),
            "risk_score":   len(inj)*3 + sum(r["days_lost"] for r in ws) + len(wq_fail)*2,
        }

    # ── QC warehouse+category rates ─────────────────────────────────────────────
    qc_wh_cat_rates = _build_qc_warehouse_cat_rates(q_filt)

    # ── Shift correlation ───────────────────────────────────────────────────────
    shift_corr = {}
    for shift in ["Morning", "Afternoon", "Night"]:
        rs  = [r for r in s_filt if r["shift"] == shift]
        inj = [r for r in rs if r["injury_reported"]]
        shift_corr[shift] = {
            "incidents":   len(rs),
            "injuries":    len(inj),
            "injury_rate": round(len(inj)/len(rs)*100, 1) if rs else 0,
            "days_lost":   sum(r["days_lost"] for r in inj),
            "severe":      sum(1 for r in rs if r["severity"] == "Severe"),
            "top_events":  dict(Counter(r["event_type"] for r in rs).most_common(3)),
        }
    for d_shift, s_shift in [("day","Morning"),("night","Night")]:
        rd     = [r for r in debriefs if r.get("shift") == d_shift]
        issues = [i for r in rd for i in r.get("issues", [])]
        shift_corr[s_shift]["global_debrief_context"] = {
            "scope":          "global_supporting — debriefs have no warehouse_id",
            "reports":        len(rd),
            "picking_errors": sum(1 for i in issues if i["category"]=="picking_errors"),
            "staffing":       sum(1 for i in issues if i["category"]=="staffing"),
            "equipment":      sum(1 for i in issues if i["category"]=="equipment"),
        }

    # ── Fire hazard deep dive ───────────────────────────────────────────────────
    fires    = [r for r in s_filt if r["event_type"] == "Fire hazard"]
    fire_inj = [r for r in fires  if r["injury_reported"]]
    fire_analysis = {
        "total_fires":    len(fires),
        "fire_injuries":  len(fire_inj),
        "fire_days_lost": sum(r["days_lost"] for r in fire_inj),
        "by_warehouse":   dict(Counter(r["warehouse_id"] for r in fires).most_common()),
        "by_area":        dict(Counter(r["area"]         for r in fires).most_common()),
        "by_equipment":   dict(Counter(normalize_equipment(r["equipment_involved"])
                                       for r in fires
                                       if r["equipment_involved"] != "None").most_common()),
        "by_shift":       dict(Counter(r["shift"] for r in fires).most_common()),
        "severe_fires":   sum(1 for r in fires if r["severity"] == "Severe"),
        "scope":          "area_local (safety has warehouse_id + area)",
    }

    # ── Forklift deep dive ──────────────────────────────────────────────────────
    forklifts = [r for r in s_filt if r["event_type"] == "Forklift collision"]
    fk_inj    = [r for r in forklifts if r["injury_reported"]]
    conv_debs = [r for r in debriefs
                 for i in r.get("issues", [])
                 if i.get("category") == "equipment"
                 and "conveyor" in i.get("description","").lower()]
    forklift_analysis = {
        "total_collisions":              len(forklifts),
        "injuries":                      len(fk_inj),
        "days_lost":                     sum(r["days_lost"] for r in fk_inj),
        "by_area":     dict(Counter(r["area"]         for r in forklifts).most_common()),
        "by_warehouse":dict(Counter(r["warehouse_id"] for r in forklifts).most_common()),
        "by_shift":    dict(Counter(r["shift"]        for r in forklifts).most_common()),
        "conveyor_debrief_issues_network": len(conv_debs),
        "conveyor_affected_zones":       list(set(r["zone"] for r in conv_debs))[:10],
        "scope_note":  "Conveyor debrief issues are zone_local but cannot be linked to warehouse",
    }

    # ── Area clusters ───────────────────────────────────────────────────────────
    area_clusters = _build_area_clusters(
        safety, qc, debrief_zone_index, voice_index, returns_signal, warehouse_id
    )

    # ── Candidate root causes ───────────────────────────────────────────────────
    candidates = _build_candidate_root_causes(
        area_clusters, debrief_zone_index, voice_index, returns_signal,
        shift_corr, fire_analysis, forklift_analysis
    )

    # ── Top debrief zones for reference (zone-local, no warehouse link) ─────────
    top_debrief_zones = {
        zone: {
            "equipment_issues": data["equipment_issues"],
            "top_themes":       dict(Counter(data["theme_counts"]).most_common(4)),
            "high_sev":         data["high_sev_issues"],
            "scope":            "zone_local (no warehouse_id available)",
        }
        for zone, data in sorted(
            debrief_zone_index.items(),
            key=lambda x: -sum(x[1]["equipment_issues"].values())
        )[:8]
    }

    return json.dumps({
        "data_scope_summary": {
            "safety":   "area_local — has warehouse_id + area",
            "qc":       "warehouse_local — has warehouse_id + category",
            "returns":  "product_bridge — linked via product_id→QC only (73 of 1000 linkable)",
            "debriefs": "zone_local — has zone, NO warehouse_id. Cannot be warehouse-local.",
            "voice":    "zone_local or warehouse_local depending on memo metadata",
        },
        "warehouse_scorecards":   wh_scores,
        "qc_warehouse_cat_rates": qc_wh_cat_rates,
        "returns_signal":         {
            "per_warehouse":     returns_signal["per_warehouse"],
            "category_defect_rates": returns_signal["category_defect_rates"],
            "linked_count":      returns_signal["linked_count"],
            "scope":             returns_signal["scope"],
        },
        "shift_correlation":      shift_corr,
        "fire_hazard_analysis":   fire_analysis,
        "forklift_analysis":      forklift_analysis,
        "top_debrief_zones":      top_debrief_zones,
        "area_or_zone_clusters":  area_clusters[:10],
        "candidate_root_causes":  candidates,
        "meta": (
            "candidate_root_causes: each has evidence_granularity and confidence_reason. "
            "Only use warehouse+area specificity when the evidence scope supports it. "
            "Debrief evidence is NEVER warehouse-local — it is zone_local at best. "
            "Returns are linked via product bridge only. "
            "Do not present global evidence as warehouse-specific in final patterns."
        ),
    }, indent=2)


# ==============================================================================
# SECTION E: TOOL REGISTRY — must be last
# ==============================================================================

ALL_TOOLS = [
    load_shift_reports,
    load_safety_incidents,
    load_qc_failures,
    load_customer_returns,
    find_product_overlap,
    compare_shift_risk,
    get_warehouse_scorecard,
    get_category_quality_report,
    load_voice_memos,
    correlate_across_sources,
]

TOOL_MAP = {t.name: t for t in ALL_TOOLS}