"""
WarehouseIQ — Action Agent Node
LangGraph node: takes root cause patterns + stats,
generates 5 deliverables using Nova Pro (structured output via LangChain).

Deliverables:
  1. Ranked action items (immediate / this_week / this_month)
  2. Slack-style alerts for critical/high patterns
  3. OSHA-style incident report for worst pattern
  4. Executive weekly trend report
  5. Voice briefing ≤55 words for Nova Sonic
"""

import json
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from state import WarehouseState


def _nova_pro() -> ChatBedrockConverse:
    return ChatBedrockConverse(
        model="amazon.nova-pro-v1:0",
        region_name="us-east-1",
        max_tokens=2000,
        temperature=0.4,
    )

def _nova_lite() -> ChatBedrockConverse:
    return ChatBedrockConverse(
        model="amazon.nova-lite-v1:0",
        region_name="us-east-1",
        max_tokens=500,
        temperature=0.4,
    )


# ── LangChain chains ───────────────────────────────────────────────────────────

_ACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a warehouse operations manager. Output ONLY valid JSON, no markdown."),
    ("human", """\
Convert these root cause patterns into prioritized action items.

Patterns:
{patterns}

Key stats:
- Safety injuries: {injuries} | Days lost: {days_lost}
- QC fail rate: {qc_fail_pct}% | Defect returns: {defect_ret_pct}%
- Staffing+picking co-occurrence: {staffing_picking} reports

Return ONLY a JSON array (no markdown):
[{{
  "action_id": "A001",
  "priority": "immediate|this_week|this_month",
  "title": "short action title",
  "description": "what to do and why in 2 sentences",
  "owner": "Safety Team|Maintenance|QC Manager|Operations|HR",
  "pattern_ref": "RC-001",
  "warehouses": ["WH-xxx"],
  "deadline_days": integer,
  "kpi": "metric that shows improvement",
  "estimated_impact": "quantified benefit"
}}]""")
])

_TREND_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are an operations director. Write a concise weekly trend report. Plain text only, no markdown."),
    ("human", """\
Write a 5-6 sentence weekly trend report for the FC Riverside warehouse network manager.

Facts:
- {total:,} records analyzed across 4 sources (shift reports, safety, QC, returns)
- Safety: {injuries} injuries, {days_lost} total days lost across 5 warehouses
- QC: {qc_fail_pct}% fail rate — {qc_failures} of {qc_total} inspections failed
- Returns: {defect_ret_pct}% defect-related ({defect_returns} of {ret_total})
- Night injuries: {night_inj} | Morning injuries: {morning_inj}
- Root cause patterns: {pattern_count} found, {immediate_count} require immediate action
- Top pattern: {top_pattern}

Open with most critical finding. Give operational health score 1-10.
Highlight 2 root causes with specific numbers. End with #1 priority for tomorrow.""")
])

_VOICE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a warehouse AI assistant. Max 55 words. 3 sentences. Conversational, no lists."),
    ("human", """\
Write a voice briefing for a warehouse supervisor. Exactly 3 sentences, max 55 words total.
Sound like a trusted advisor, not a report. Start with a time-appropriate greeting.

Facts:
- {total:,} records analyzed
- {pattern_count} patterns found, {immediate_count} immediate actions needed
- Top issue: {top_pattern}
- First action: {first_action}
- {injuries} injuries on record, {qc_fail_pct}% QC fail rate""")
])

_INCIDENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a safety officer. Write a formal OSHA-style incident report. Plain text, no markdown."),
    ("human", """\
Write a formal safety incident summary report (3 paragraphs) for this root cause pattern.

Pattern:
{pattern}

Para 1: Describe recurring issue, affected locations, frequency (use specific numbers)
Para 2: Evidence from multiple data sources (safety logs, debriefs, QC, returns)
Para 3: Required corrective actions, accountable owners, deadlines""")
])


def _parse_json(s: str):
    return json.loads(s.replace("```json","").replace("```","").strip())


EMOJI = {"critical":"🚨","high":"⚠️","medium":"⚡","low":"ℹ️"}


# ── LangGraph Node ─────────────────────────────────────────────────────────────

def action_node(state: WarehouseState) -> dict:
    """
    LangGraph node: generates all 5 deliverables using LangChain chains.
    """
    patterns = state["patterns"]
    stats    = state["stats"]
    records  = state["enriched_records"]

    s_safety  = stats.get("safety",{})
    s_qc      = stats.get("qc",{})
    s_returns = stats.get("returns",{})
    s_deb     = stats.get("debriefs",{})

    pro  = _nova_pro()
    lite = _nova_lite()

    print(f"\n[Action Agent] Generating deliverables for {len(patterns)} patterns...")

    # 1. Action items
    print("  [Action] → Ranked action items (Nova Pro)...")
    action_chain = _ACTION_PROMPT | pro | StrOutputParser()
    actions_raw  = action_chain.invoke({
        "patterns":       json.dumps(patterns, indent=2)[:3000],
        "injuries":       s_safety.get("injuries",0),
        "days_lost":      s_safety.get("total_days_lost",0),
        "qc_fail_pct":    s_qc.get("fail_rate_pct",0),
        "defect_ret_pct": s_returns.get("defect_rate_pct",0),
        "staffing_picking": s_deb.get("staffing_AND_picking",0),
    })
    action_items = _parse_json(actions_raw)

    # 2. Slack alerts (no LLM needed — derive from patterns)
    alerts = []
    for p in patterns:
        if p.get("severity") not in ("critical","high"):
            continue
        alerts.append({
            "alert_id":   f"ALERT-{p.get('pattern_id','X')}",
            "severity":   p["severity"],
            "emoji":      EMOJI.get(p["severity"],"⚠️"),
            "title":      f"{EMOJI.get(p['severity'],'')} {p.get('title','')}",
            "warehouses": p.get("warehouses",[]),
            "shifts":     p.get("shifts_affected","All"),
            "sources":    p.get("data_sources",[]),
            "occurrences":p.get("occurrence_count",0),
            "summary":    p.get("description",""),
            "top_action": p.get("actions",[{}])[0].get("action","Review immediately"),
        })

    # 3. Trend report
    print("  [Action] → Executive trend report (Nova Pro)...")
    imm_count = sum(1 for a in action_items if a.get("priority")=="immediate")
    trend_chain = _TREND_PROMPT | pro | StrOutputParser()
    trend_report = trend_chain.invoke({
        "total":         stats.get("total_records",4000),
        "injuries":      s_safety.get("injuries",0),
        "days_lost":     s_safety.get("total_days_lost",0),
        "qc_fail_pct":   s_qc.get("fail_rate_pct",0),
        "qc_failures":   s_qc.get("failures",0),
        "qc_total":      s_qc.get("total",0),
        "defect_ret_pct":s_returns.get("defect_rate_pct",0),
        "defect_returns":s_returns.get("defect_related",0),
        "ret_total":     s_returns.get("total",0),
        "night_inj":     s_safety.get("night_injuries",0),
        "morning_inj":   s_safety.get("morning_injuries",0),
        "pattern_count": len(patterns),
        "immediate_count":imm_count,
        "top_pattern":   patterns[0].get("title","") if patterns else "",
    })

    # 4. Voice briefing
    print("  [Action] → Voice briefing (Nova Lite)...")
    voice_chain = _VOICE_PROMPT | lite | StrOutputParser()
    voice_briefing = voice_chain.invoke({
        "total":         stats.get("total_records",4000),
        "pattern_count": len(patterns),
        "immediate_count":imm_count,
        "top_pattern":   patterns[0].get("title","") if patterns else "equipment issues",
        "first_action":  action_items[0].get("title","review safety logs") if action_items else "review logs",
        "injuries":      s_safety.get("injuries",0),
        "qc_fail_pct":   s_qc.get("fail_rate_pct",0),
    })

    # 5. Incident report for worst pattern
    incident_report = None
    critical = [p for p in patterns if p.get("severity") in ("critical","high")]
    if critical:
        print(f"  [Action] → OSHA incident report for {critical[0].get('pattern_id')}...")
        inc_chain = _INCIDENT_PROMPT | pro | StrOutputParser()
        incident_report = inc_chain.invoke({
            "pattern": json.dumps(critical[0], indent=2)
        })

    immediate = [a for a in action_items if a.get("priority")=="immediate"]
    print(f"[Action Agent] ✓ {len(action_items)} actions | {len(alerts)} alerts | {len(immediate)} immediate")

    return {
        "action_items":    action_items,
        "alerts":          alerts,
        "trend_report":    trend_report,
        "voice_briefing":  voice_briefing,
        "incident_report": incident_report,
        "current_step":    "action",
        "progress":        85,
        "messages":        [SystemMessage(
            content=f"Action agent complete: {len(action_items)} actions generated "
                    f"({len(immediate)} immediate), {len(alerts)} alerts triggered. "
                    f"Voice briefing ready for Nova Sonic."
        )],
    }