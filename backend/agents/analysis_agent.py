"""
WarehouseIQ — Analysis Agent Node
LangGraph node: uses ChatBedrockConverse (Nova Lite) to enrich a
stratified sample of records with sentiment, themes, anomaly detection.
Computes full raw stats across all 4000 records without AI.
"""

import json, random
from collections import Counter, defaultdict
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from state import WarehouseState


# ── LangChain LLM setup ────────────────────────────────────────────────────────

def _nova_lite() -> ChatBedrockConverse:
    return ChatBedrockConverse(
        model="amazon.nova-lite-v1:0",
        region_name="us-east-1",
        max_tokens=500,
        temperature=0.2,
    )


# ── Prompt ─────────────────────────────────────────────────────────────────────

ENRICH_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a warehouse operations analyst. Analyze records and return ONLY valid JSON, no markdown."),
    ("human", """\
Source: {source_type} | Date: {date} | Location: {location} | Shift: {shift}

Record:
\"\"\"{text}\"\"\"

Return ONLY this JSON:
{{
  "sentiment": "positive|neutral|negative|mixed",
  "sentiment_score": float -1.0 to 1.0,
  "themes": ["2-3 of: ergonomics, equipment_failure, staffing_shortage, picking_errors, safety_hazard, quality_defect, returns_damage, overexertion, inventory_mismatch, process_failure"],
  "anomaly": true|false,
  "anomaly_reason": "one sentence or null",
  "issues": [{{"type":"safety|equipment|staffing|quality|returns","description":"one sentence","severity":"low|medium|high|critical"}}],
  "requires_followup": true|false,
  "summary": "one sentence key insight"
}}""")
])


def _enrich_one(rec: dict, llm: ChatBedrockConverse) -> dict:
    loc = rec.get("warehouse_id") or rec.get("zone") or "—"
    chain = ENRICH_PROMPT | llm
    resp  = chain.invoke({
        "source_type": rec.get("source_type","?"),
        "date":        rec.get("date","?"),
        "location":    loc,
        "shift":       rec.get("shift","?"),
        "text":        (rec.get("text") or "")[:400],
    })
    raw = resp.content
    parsed = json.loads(raw.replace("```json","").replace("```","").strip())
    return {**rec, "analysis": parsed}


def _stratified_sample(records: list[dict], n: int = 200) -> list[dict]:
    by_type: dict = defaultdict(list)
    for r in records:
        by_type[r["source_type"]].append(r)
    per_type = max(1, n // len(by_type))
    out = []
    for recs in by_type.values():
        out.extend(random.sample(recs, min(per_type, len(recs))))
    return out


# ── Full-dataset raw stats (no AI needed, uses all 4000 records) ──────────────

def _raw_stats(records: list[dict]) -> dict:
    debriefs = [r for r in records if r["source_type"] == "debrief"]
    safety   = [r for r in records if r["source_type"] == "safety"]
    qc       = [r for r in records if r["source_type"] == "qc"]
    returns  = [r for r in records if r["source_type"] == "returns"]

    DEFECT  = {"Item damaged","Defective product","Wrong item received","Missing parts"}
    injuries    = [r for r in safety if r.get("injury_reported")]
    night_inj   = [r for r in safety if r.get("injury_reported") and r.get("shift","").lower()=="night"]
    qc_fail     = [r for r in qc if r.get("qc_status")=="Fail"]
    qc_flagged  = [r for r in qc if r.get("flagged_for_review")=="Yes"]
    ret_defect  = [r for r in returns if r.get("return_reason") in DEFECT]
    all_issues  = [i for r in debriefs for i in r.get("issues",[])]
    night_deb   = [r for r in debriefs if r.get("shift")=="night"]
    staff_pick  = [r for r in debriefs
                   if any(i["category"]=="staffing"       for i in r.get("issues",[]))
                   and any(i["category"]=="picking_errors" for i in r.get("issues",[]))]

    return {
        "total_records": len(records),
        "by_type":       dict(Counter(r["source_type"] for r in records)),
        "by_severity":   dict(Counter(r["severity"]    for r in records)),
        "safety": {
            "total":            len(safety),
            "injuries":         len(injuries),
            "night_injuries":   len(night_inj),
            "morning_injuries": sum(1 for r in safety if r.get("injury_reported") and r.get("shift","").lower()=="morning"),
            "total_days_lost":  sum(r.get("days_lost",0) for r in safety),
            "by_event_type":    dict(Counter(r["event_type"] for r in safety).most_common(8)),
            "by_equipment":     dict(Counter(r["equipment_involved"] for r in safety
                                            if r.get("equipment_involved","None")!="None").most_common(5)),
            "by_warehouse":     dict(Counter(r["warehouse_id"] for r in safety).most_common()),
            "by_shift":         dict(Counter(r["shift"] for r in safety)),
        },
        "qc": {
            "total":             len(qc),
            "failures":          len(qc_fail),
            "fail_rate_pct":     round(len(qc_fail)/len(qc)*100,1) if qc else 0,
            "flagged":           len(qc_flagged),
            "by_defect_type":    dict(Counter(r["defect_type"] for r in qc_fail).most_common(7)),
            "by_category":       dict(Counter(r["category"]    for r in qc).most_common()),
            "fail_by_warehouse": dict(Counter(r["warehouse_id"] for r in qc_fail).most_common()),
            "by_inspector":      dict(Counter(r["inspector_level"] for r in qc_fail).most_common()),
        },
        "returns": {
            "total":           len(returns),
            "defect_related":  len(ret_defect),
            "defect_rate_pct": round(len(ret_defect)/len(returns)*100,1) if returns else 0,
            "by_reason":       dict(Counter(r["return_reason"] for r in returns).most_common()),
            "by_category":     dict(Counter(r["category"]      for r in returns).most_common()),
            "avg_return_days": round(sum(r.get("return_days",0) for r in returns)/len(returns),1) if returns else 0,
            "damaged_condition":sum(1 for r in returns if r.get("condition")=="Damaged"),
        },
        "debriefs": {
            "total":                len(debriefs),
            "night_shift":          len(night_deb),
            "day_shift":            len(debriefs)-len(night_deb),
            "issue_categories":     dict(Counter(i["category"] for i in all_issues).most_common()),
            "high_severity_issues": sum(1 for i in all_issues if i.get("severity",1)>=4),
            "staffing_AND_picking": len(staff_pick),
            "top_zones_picking":    dict(Counter(
                r["zone"] for r in debriefs
                if any(i["category"]=="picking_errors" and i.get("severity",1)>=3
                       for i in r.get("issues",[]))
            ).most_common(6)),
        },
    }


# ── LangGraph Node ─────────────────────────────────────────────────────────────

def analysis_node(state: WarehouseState) -> dict:
    """
    LangGraph node: enriches a stratified sample with Nova Lite,
    computes full raw stats, returns enriched records + stats.
    """
    records = state["raw_records"]
    print(f"\n[Analysis Agent] {len(records):,} records — sampling 200 for Nova Lite enrichment...")

    # Raw stats (fast, no AI)
    stats = _raw_stats(records)

    # AI enrichment on sample
    llm    = _nova_lite()
    sample = _stratified_sample(records, 200)
    enriched_sample = []

    for i, rec in enumerate(sample):
        try:
            enriched_sample.append(_enrich_one(rec, llm))
        except Exception as e:
            enriched_sample.append(rec)
            print(f"  [{i+1}] error: {e}")
        if (i+1) % 25 == 0:
            print(f"  [{i+1}/{len(sample)}] enriched")

    # AI-derived stats from sample
    sentiments  = [r["analysis"]["sentiment"] for r in enriched_sample if "analysis" in r]
    themes_flat = [t for r in enriched_sample if "analysis" in r
                   for t in r["analysis"].get("themes",[])]
    anomalies   = [r for r in enriched_sample if r.get("analysis",{}).get("anomaly")]

    stats["ai"] = {
        "sample_size":      len(enriched_sample),
        "sentiment":        {k: sentiments.count(k) for k in ["positive","neutral","negative","mixed"]},
        "top_themes":       Counter(themes_flat).most_common(10),
        "anomaly_count":    len(anomalies),
        "requires_followup":sum(1 for r in enriched_sample if r.get("analysis",{}).get("requires_followup")),
    }

    # Merge: enriched sample + plain remaining records
    enriched_ids = {r["id"] for r in enriched_sample}
    all_enriched = enriched_sample + [r for r in records if r["id"] not in enriched_ids]

    print(f"[Analysis Agent] ✓ Anomalies: {len(anomalies)} | "
          f"QC fail: {stats['qc']['fail_rate_pct']}% | "
          f"Defect returns: {stats['returns']['defect_rate_pct']}%")

    return {
        "enriched_records": all_enriched,
        "stats":            stats,
        "current_step":     "analysis",
        "progress":         40,
        "messages":         [SystemMessage(
            content=f"Analysis complete. {len(anomalies)} anomalies found in sample. "
                    f"QC fail rate: {stats['qc']['fail_rate_pct']}%. "
                    f"Defect return rate: {stats['returns']['defect_rate_pct']}%. "
                    f"Top themes: {[t for t,_ in stats['ai']['top_themes'][:3]]}"
        )],
    }