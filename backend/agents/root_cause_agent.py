"""
WarehouseIQ — Root Cause Agent Node

Key design principles:
1. correlate_across_sources() is called programmatically — model cannot skip it.
2. Tool-call budget (10) is enforced by counting actual calls.
3. Investigation uses tool-bound Nova Pro. Final output uses plain unbound model.
4. JSON extraction is robust: handles string content, list content blocks, nested dicts.
5. Final output prompt explicitly teaches the model to respect evidence_granularity —
   only claim locality when the evidence scope actually supports it.
6. Validation + one repair pass if schema requirements fail.
"""

import json
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from state import WarehouseState
from tools.warehouse_tools import ALL_TOOLS, TOOL_MAP


# ==============================================================================
# PROMPTS
# ==============================================================================

INVESTIGATION_SYSTEM = """You are a warehouse safety and operations investigator for Amazon FC Riverside.

You have just received pre-correlated cross-source evidence from correlate_across_sources().
It contains candidate_root_causes: specific hypotheses tied to warehouse + area +
equipment + shift, backed by multi-source evidence. Each candidate has:
  - evidence_granularity: how locally the evidence actually matches
  - confidence_reason: why confidence is what it is
  - hypothesis: wording that honestly reflects evidence scope

CRITICAL EVIDENCE RULES (read these carefully):
- Debrief records have zone but NO warehouse_id. They are zone_local at best,
  NEVER warehouse-local. Do not claim debrief evidence proves something about
  a specific warehouse unless voice memos or safety data also support it.
- Returns can only be linked to warehouses via the product_id → QC bridge (73 records).
  Do not claim returns are warehouse-specific without this bridge.
- Safety logs have warehouse_id + area — this is your most reliable local evidence.
- QC has warehouse_id + category — reliable at warehouse level.

YOUR ROLE:
1. Read candidate_root_causes carefully — these are your starting hypotheses.
2. Use remaining tool calls to DEEPEN specific candidates:
   - get_warehouse_scorecard() for the 1-2 worst warehouses — gets area breakdown
   - load_safety_incidents(event_type="Fire hazard") for fire specifics
   - find_product_overlap() for QC→returns product pipeline
   - get_category_quality_report() for worst QC category
   - compare_shift_risk() if shift signal needs depth
3. Do NOT re-call correlate_across_sources() — result already injected.
4. Do NOT upgrade your evidence claims beyond what the data scope supports."""


FINAL_OUTPUT_SYSTEM = """You are producing the final root cause analysis JSON for WarehouseIQ.

EVIDENCE GRANULARITY RULES — follow these exactly:

1. SAFETY LOGS (area_local): You can say "In WH-305 Packing Zone..." because
   safety logs have warehouse_id + area. This is your strongest local evidence.

2. QC DATA (warehouse_local): You can say "At WH-305, QC failures show..."
   but NOT "In WH-305 Packing Zone QC failures" because QC doesn't have area.

3. DEBRIEF DATA (zone_local, NO warehouse link): You can say "Zone C3 shows
   conveyor equipment issues" but NEVER "WH-305 Zone C3" because debriefs have
   no warehouse_id. When debrief evidence is global (aggregated across zones),
   say "network-wide debrief evidence suggests..." not "at WH-305..."

4. RETURNS (product_bridge only): You can say "Returns linked via product bridge
   to WH-305 show defect returns in the Sports category" — but only because
   that link was made through matching product_ids in QC records. Do not claim
   returns are warehouse-specific otherwise.

5. WHEN EVIDENCE IS MIXED: Be explicit. E.g.:
   "Safety evidence is specific to WH-101 Receiving Dock (area_local).
   Debrief evidence showing conveyor issues is from zones A1/C3 and cannot
   be confirmed as specific to WH-101, but supports the pattern."

PATTERN QUALITY BAR:
- BAD: "WH-305 Packing Zone shows conveyor issues causing QC failures"
  (wrong if debrief is global and QC is only warehouse-level)
- GOOD: "WH-305 Packing Zone shows forklift collision concentration (safety, area_local).
  QC failures at WH-305 are highest for Electronics/Home (warehouse_local).
  Network-wide debrief data shows conveyor stoppages in zones C3/A1, suggesting
  similar dynamics may exist here but cannot be confirmed without zone-to-warehouse mapping."

Produce 5-7 patterns that are honest about evidence scope while still being specific
and actionable where the evidence truly supports specificity."""


ROOT_CAUSE_SCHEMA = """
Return ONLY a valid JSON array. No markdown. No preamble.

[
  {
    "pattern_id": "RC-001",
    "title": "Specific title: equipment/event + warehouse + area max 12 words",
    "severity": "critical|high|medium|low",
    "data_sources": ["safety","debrief","qc","returns","voice_memo"],
    "warehouses": ["WH-xxx"],
    "shifts_affected": "Night|Morning|Afternoon|All",
    "occurrence_count": <integer>,
    "description": "3-4 sentences. Specific numbers. Which warehouse, which area. What sources support it and at what granularity.",
    "root_cause": "2-3 sentences. Causal chain. What causes what. Be explicit about evidence scope.",
    "evidence": [
      "Safety (area_local): specific fact with number",
      "QC (warehouse_local) or Debrief (zone_local, no warehouse link): specific fact",
      "Returns (product_bridge) or Voice or Global debrief: specific fact"
    ],
    "actions": [
      {
        "action": "Concrete action with specific location",
        "owner": "Safety Team|Maintenance|QC Manager|Operations|HR",
        "urgency": "immediate|this_week|this_month"
      }
    ],
    "impact": "Quantified expected improvement"
  }
]

REQUIREMENTS:
- 5-7 patterns
- At least 2 safety-focused (describe specific safety event types with counts)
- At least 2 cross-source (span 2+ data sources)
- At least 1 equipment-focused (specific equipment name)
- At least 1 that mentions evidence granularity explicitly in description or root_cause
- severity: only critical|high|medium|low
- evidence list: at least 2 bullets, each labeled with source and scope"""


# ==============================================================================
# ROBUST JSON EXTRACTOR
# ==============================================================================

def _extract_json_from_content(content) -> list:
    """
    Extract JSON array from model output.
    Handles:
    - Plain string content
    - LangChain/Bedrock content block lists: [{"type":"text","text":"..."}]
    - Nested dicts with "text" key
    - Strips markdown fences
    - Finds first [...] block
    """
    # Resolve content to a plain string
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        # Bedrock content blocks: [{"type":"text","text":"..."}, ...]
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text","") or block.get("content","") or "")
            elif isinstance(block, str):
                parts.append(block)
        text = "\n".join(parts)
    elif isinstance(content, dict):
        text = content.get("text","") or content.get("content","") or json.dumps(content)
    else:
        text = str(content)

    # Strip markdown fences
    text = text.replace("```json","").replace("```","").strip()

    # Find first [...] block
    start = text.find("[")
    end   = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON array found in model output. Content preview: {text[:200]}")

    return json.loads(text[start:end+1])


# ==============================================================================
# OUTPUT VALIDATION
# ==============================================================================

VALID_SEVERITIES = {"critical","high","medium","low"}


def _validate_patterns(patterns: list) -> tuple:
    """Returns (is_valid: bool, errors: list[str])."""
    errors = []
    if not isinstance(patterns, list):
        return False, ["Output is not a JSON array"]

    if len(patterns) < 5:
        errors.append(f"Too few patterns: {len(patterns)} (need 5-7)")
    if len(patterns) > 7:
        errors.append(f"Too many patterns: {len(patterns)} (need 5-7)")

    safety_p = [p for p in patterns if "safety" in p.get("data_sources",[])]
    cross_p  = [p for p in patterns if len(p.get("data_sources",[])) > 1]
    equip_kw = {"Conveyor","Forklift","Pallet Jack","Scanner","conveyor","forklift",
                "pallet jack","scanner","equipment","Equipment"}
    equip_p  = [p for p in patterns
                if any(kw in (p.get("title","") + " " + p.get("root_cause",""))
                       for kw in equip_kw)]

    if len(safety_p) < 2:
        errors.append(f"Need ≥2 safety patterns, got {len(safety_p)}")
    if len(cross_p) < 2:
        errors.append(f"Need ≥2 cross-source patterns, got {len(cross_p)}")
    if len(equip_p) < 1:
        errors.append(f"Need ≥1 equipment-focused pattern")

    required = ["pattern_id","title","severity","data_sources","warehouses",
                "shifts_affected","occurrence_count","description",
                "root_cause","evidence","actions","impact"]
    for i, p in enumerate(patterns):
        if not isinstance(p, dict):
            errors.append(f"Pattern {i} is not an object"); continue
        missing = [f for f in required if f not in p]
        if missing:
            errors.append(f"Pattern {i} missing: {missing}")
        if p.get("severity") not in VALID_SEVERITIES:
            errors.append(f"Pattern {i} invalid severity: {p.get('severity')}")
        if not isinstance(p.get("evidence"), list) or len(p.get("evidence",[])) < 2:
            errors.append(f"Pattern {i} needs ≥2 evidence items")
        if not isinstance(p.get("actions"), list) or len(p.get("actions",[])) < 1:
            errors.append(f"Pattern {i} needs ≥1 action")

    return len(errors) == 0, errors


# ==============================================================================
# MODEL FACTORIES
# ==============================================================================

def _nova_pro_bound() -> ChatBedrockConverse:
    """Tool-bound model for investigation loop."""
    return ChatBedrockConverse(
        model="amazon.nova-pro-v1:0",
        region_name="us-east-1",
        max_tokens=4000,
        temperature=0.2,
    ).bind_tools(ALL_TOOLS)


def _nova_pro_unbound() -> ChatBedrockConverse:
    """Plain model for final JSON output — cannot call tools."""
    return ChatBedrockConverse(
        model="amazon.nova-pro-v1:0",
        region_name="us-east-1",
        max_tokens=4000,
        temperature=0.15,
    )


# ==============================================================================
# INVESTIGATION LOOP
# ==============================================================================

def _run_investigation(llm_bound, ingestion_summary: dict,
                       analysis_stats: dict, max_tool_calls: int = 10) -> tuple:
    """
    Step 1 (programmatic): Call correlate_across_sources() and inject result.
    Step 2 (agent-driven):  Model chooses follow-up tools (budget: max_tool_calls - 1).
    Step 3 (unbound model): Generate final validated JSON.
    """
    s = analysis_stats

    # ── Step 1: Programmatic correlation call ───────────────────────────────────
    print("  [RootCause] Step 1: Programmatic correlate_across_sources()...")
    corr_tool   = TOOL_MAP["correlate_across_sources"]
    corr_result = corr_tool.invoke({})
    print(f"  [RootCause] Correlation: {len(corr_result):,} chars")

    fake_tool_id = "forced-corr-001"
    messages = [
        SystemMessage(content=INVESTIGATION_SYSTEM),
        HumanMessage(content=(
            f"Dataset: {ingestion_summary.get('total',4000):,} total records.\n"
            f"Safety: {s.get('safety',{}).get('total',0)} records, "
            f"{s.get('safety',{}).get('injuries',0)} injuries.\n"
            f"QC: {s.get('qc',{}).get('fail_rate_pct',0)}% fail rate.\n"
            f"Returns: {s.get('returns',{}).get('defect_rate_pct',0)}% defect-related.\n\n"
            "correlate_across_sources() has been run. Read candidate_root_causes carefully. "
            "Each candidate has evidence_granularity and confidence_reason. "
            "Use your tool calls to deepen the most promising candidates."
        )),
        AIMessage(
            content="",
            tool_calls=[{"id": fake_tool_id,
                         "name": "correlate_across_sources", "args": {}}]
        ),
        ToolMessage(content=corr_result, tool_call_id=fake_tool_id,
                    name="correlate_across_sources"),
    ]
    tool_calls_used = 1

    # ── Step 2: Agent-driven drill-down ─────────────────────────────────────────
    for iteration in range(20):
        remaining = max_tool_calls - tool_calls_used
        if remaining <= 0:
            print(f"  [RootCause] Budget exhausted ({max_tool_calls} calls used)")
            break

        print(f"  [RootCause] Iter {iteration+1} | used: {tool_calls_used}/{max_tool_calls}")
        response = llm_bound.invoke(messages)
        messages.append(response)

        tool_calls = getattr(response, "tool_calls", []) or []
        if not tool_calls:
            print(f"  [RootCause] Agent stopped voluntarily at iter {iteration+1}")
            break

        calls_to_process = tool_calls[:remaining]
        print(f"  [RootCause] → {[tc['name'] for tc in calls_to_process]}")
        tool_calls_used += len(calls_to_process)

        for tc in calls_to_process:
            # Block re-calling correlate — already done
            if tc["name"] == "correlate_across_sources":
                messages.append(ToolMessage(
                    content=json.dumps({"note": "Already called. Use the injected result above."}),
                    tool_call_id=tc["id"], name=tc["name"],
                ))
                tool_calls_used -= 1
                continue

            tool_fn = TOOL_MAP.get(tc["name"])
            if tool_fn:
                try:
                    result = tool_fn.invoke(tc.get("args", {}))
                    messages.append(ToolMessage(
                        content=result, tool_call_id=tc["id"], name=tc["name"],
                    ))
                    print(f"    ✓ {tc['name']}({tc.get('args',{})}) → {len(result):,} chars")
                except Exception as e:
                    messages.append(ToolMessage(
                        content=json.dumps({"error": str(e)}),
                        tool_call_id=tc["id"], name=tc["name"],
                    ))
            else:
                messages.append(ToolMessage(
                    content=json.dumps({"error": f"Unknown tool: {tc['name']}"}),
                    tool_call_id=tc["id"], name=tc["name"],
                ))

    # ── Step 3: Unbound model generates final JSON ──────────────────────────────
    print(f"  [RootCause] Step 3: Final JSON generation ({tool_calls_used} tool calls used)...")

    tool_summary = "\n".join(
        f"- {m.name}: {len(m.content):,} chars"
        for m in messages if isinstance(m, ToolMessage)
    )

    final_messages = [
        SystemMessage(content=FINAL_OUTPUT_SYSTEM),
        HumanMessage(content=(
            f"Investigation complete. Evidence collected:\n{tool_summary}\n\n"
            "Produce the final root cause JSON array. "
            "Respect evidence granularity labels — do not claim warehouse-area specificity "
            "unless safety logs (area_local) support it at that location.\n\n"
            + ROOT_CAUSE_SCHEMA
        )),
        # Pass all tool results as context
        *[m for m in messages if isinstance(m, ToolMessage)],
        HumanMessage(content="Output the JSON array now. No markdown. No preamble."),
    ]

    llm_plain  = _nova_pro_unbound()
    final_resp = llm_plain.invoke(final_messages)
    patterns   = _extract_json_from_content(final_resp.content)
    return patterns, messages


def _repair_patterns(patterns: list, errors: list) -> list:
    """One repair pass using unbound model. Returns repaired or original."""
    print(f"  [RootCause] Repair pass: {len(errors)} errors")
    llm = _nova_pro_unbound()
    repair_msgs = [
        SystemMessage(content=FINAL_OUTPUT_SYSTEM),
        HumanMessage(content=(
            "The previous output had validation errors:\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\n\nInvalid output:\n"
            + json.dumps(patterns, indent=2)
            + "\n\nRequired schema:\n"
            + ROOT_CAUSE_SCHEMA
            + "\n\nFix all errors. Return ONLY the corrected JSON array."
        )),
    ]
    try:
        resp     = llm.invoke(repair_msgs)
        repaired = _extract_json_from_content(resp.content)
        ok, errs = _validate_patterns(repaired)
        if ok:
            print("  [RootCause] Repair successful")
            return repaired
        print(f"  [RootCause] Repair still has errors: {errs} — using best-effort original")
        return patterns
    except Exception as e:
        print(f"  [RootCause] Repair error: {e} — using original")
        return patterns


# ==============================================================================
# LANGGRAPH NODE
# ==============================================================================

def root_cause_node(state: WarehouseState) -> dict:
    print(f"\n[Root Cause Agent] Starting — "
          f"{len(state.get('enriched_records',[]))} records, {len(ALL_TOOLS)} tools")

    try:
        patterns, messages = _run_investigation(
            _nova_pro_bound(),
            ingestion_summary=state["ingestion_summary"],
            analysis_stats=state["stats"],
            max_tool_calls=10,
        )
    except Exception as e:
        print(f"[Root Cause Agent] Error: {e}")
        return {"error": f"Root cause failed: {e}",
                "current_step": "root_cause", "progress": 60}

    is_valid, errors = _validate_patterns(patterns)
    if not is_valid:
        print(f"[Root Cause Agent] Validation failed: {errors}")
        patterns   = _repair_patterns(patterns, errors)
        is_valid, errors = _validate_patterns(patterns)

    safety_p   = [p for p in patterns if "safety" in p.get("data_sources",[])]
    cross_p    = [p for p in patterns if len(p.get("data_sources",[])) > 1]
    critical_h = [p for p in patterns if p.get("severity") in ("critical","high")]

    print(f"[Root Cause Agent] ✓ {len(patterns)} patterns | "
          f"safety:{len(safety_p)} cross:{len(cross_p)} "
          f"high/crit:{len(critical_h)} valid:{is_valid}")

    return {
        "patterns": patterns,
        "pattern_stats": {
            "total":              len(patterns),
            "critical":           sum(1 for p in patterns if p.get("severity")=="critical"),
            "high":               sum(1 for p in patterns if p.get("severity")=="high"),
            "cross_source":       len(cross_p),
            "safety_patterns":    len(safety_p),
            "warehouses_flagged": len({w for p in patterns for w in p.get("warehouses",[])}),
            "validated":          is_valid,
        },
        "current_step": "root_cause",
        "progress":     65,
        "messages":     [SystemMessage(
            content=f"Root cause complete: {len(patterns)} patterns, "
                    f"safety={len(safety_p)}, cross_source={len(cross_p)}, valid={is_valid}"
        )],
    }