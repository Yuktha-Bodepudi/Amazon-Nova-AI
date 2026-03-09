"""
WarehouseIQ — Root Cause Agent Node (TRULY AGENTIC)
This is where LangGraph + LangChain tool-calling shines.

Instead of sending a fixed prompt, Nova Pro autonomously:
1. Decides which warehouse tools to call based on context
2. Iterates: calls tool → sees result → decides what else to investigate
3. Forms root cause hypotheses grounded in real data it fetched itself

This is a ReAct-style agent loop running inside a LangGraph node.
"""

import json
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from state import WarehouseState
from tools.warehouse_tools import ALL_TOOLS, TOOL_MAP


SYSTEM_PROMPT = """You are a senior warehouse operations analyst for Amazon's FC Riverside network (WH-101 to WH-512).

You have access to tools that query real operational data across 4 sources:
- Shift debrief reports (1,000 records: zones A1-D6, day/night shifts)  
- Safety incident logs (1,000 records: 5 warehouses, 601 injuries, 8 event types)
- QC inspection flags (1,000 records: 83% fail rate, 5 product categories)
- Customer returns (1,000 records: 34.7% defect-related)

YOUR TASK: Autonomously investigate to find ROOT CAUSES that connect multiple data sources.

STRATEGY:
1. Start broad — compare all warehouses, check shift risk, find product overlap
2. Drill down — once you identify a hot spot, get its specific scorecard
3. Connect dots — look for patterns that span safety + QC + returns + debriefs
4. Form 5-6 specific root causes with data-backed evidence

Call tools iteratively. Each tool call gives you real data. Use it to decide what to investigate next.
Think like a detective — follow the evidence.

After your investigation, output your findings as a JSON array of root causes."""

ROOT_CAUSE_SCHEMA = """\
After your tool investigation, return ONLY a valid JSON array:
[
  {
    "pattern_id": "RC-001",
    "title": "Short title max 12 words",
    "severity": "critical|high|medium|low",
    "data_sources": ["debrief","safety","qc","returns"],
    "warehouses": ["WH-xxx"],
    "shifts_affected": "Night|Morning|All",
    "occurrence_count": integer,
    "description": "2-3 sentences with specific numbers you found via tools",
    "root_cause": "1-2 sentences — the specific underlying cause",
    "evidence": ["fact with number 1","fact with number 2","fact with number 3"],
    "actions": [
      {"action":"specific action","owner":"Safety|Maintenance|QC|Operations|HR","urgency":"immediate|this_week|this_month"}
    ],
    "impact": "What measurably improves if this is fixed"
  }
]"""


def _nova_pro_with_tools() -> ChatBedrockConverse:
    return ChatBedrockConverse(
        model="amazon.nova-pro-v1:0",
        region_name="us-east-1",
        max_tokens=3000,
        temperature=0.35,
    ).bind_tools(ALL_TOOLS)


def _run_agentic_loop(llm_with_tools: ChatBedrockConverse,
                      ingestion_summary: dict,
                      analysis_stats: dict,
                      max_iterations: int = 8) -> list[dict]:
    """
    ReAct-style agentic loop:
    Agent calls tools → sees results → calls more tools → eventually outputs root causes.
    """
    context = (
        f"Dataset overview:\n"
        f"- {ingestion_summary.get('total',4000):,} total records across 4 sources\n"
        f"- QC fail rate: {analysis_stats.get('qc',{}).get('fail_rate_pct',83)}%\n"
        f"- Safety injuries: {analysis_stats.get('safety',{}).get('injuries',0)}\n"
        f"- Defect returns: {analysis_stats.get('returns',{}).get('defect_rate_pct',0)}%\n"
        f"- Night injuries: {analysis_stats.get('safety',{}).get('night_injuries',0)}\n"
        f"- Staffing+picking co-occurrence: "
        f"{analysis_stats.get('debriefs',{}).get('staffing_AND_picking',0)} reports\n\n"
        f"Begin your investigation. Call tools to gather evidence, then output your root cause findings."
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=context),
    ]

    for iteration in range(max_iterations):
        print(f"  [RootCause] Iteration {iteration+1}/{max_iterations}...")
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        # Check if agent wants to call tools
        tool_calls = getattr(response, "tool_calls", []) or []

        if not tool_calls:
            # Agent is done with tool-calling — extract final JSON
            print(f"  [RootCause] Agent finished after {iteration+1} iterations")
            break

        # Execute tool calls and feed results back
        print(f"  [RootCause] Agent calling {len(tool_calls)} tool(s): "
              f"{[tc['name'] for tc in tool_calls]}")

        for tc in tool_calls:
            tool_fn = TOOL_MAP.get(tc["name"])
            if tool_fn:
                try:
                    result = tool_fn.invoke(tc.get("args", {}))
                    messages.append(ToolMessage(
                        content=result,
                        tool_call_id=tc["id"],
                        name=tc["name"],
                    ))
                    print(f"    → {tc['name']} returned {len(result)} chars")
                except Exception as e:
                    messages.append(ToolMessage(
                        content=json.dumps({"error": str(e)}),
                        tool_call_id=tc["id"],
                        name=tc["name"],
                    ))
            else:
                messages.append(ToolMessage(
                    content=json.dumps({"error": f"Unknown tool: {tc['name']}"}),
                    tool_call_id=tc["id"],
                    name=tc["name"],
                ))

    # Request final structured output
    messages.append(HumanMessage(
        content=f"Based on your investigation, now output your root cause findings.\n{ROOT_CAUSE_SCHEMA}"
    ))
    final = llm_with_tools.invoke(messages)
    raw   = final.content
    patterns = json.loads(raw.replace("```json","").replace("```","").strip())
    return patterns


# ── LangGraph Node ─────────────────────────────────────────────────────────────

def root_cause_node(state: WarehouseState) -> dict:
    """
    LangGraph node: autonomous tool-calling ReAct loop.
    Nova Pro decides what to investigate, calls tools iteratively,
    then synthesizes cross-source root causes.
    """
    print(f"\n[Root Cause Agent] Starting autonomous investigation "
          f"({len(state['enriched_records']):,} records, {len(ALL_TOOLS)} tools available)...")

    llm = _nova_pro_with_tools()

    try:
        patterns = _run_agentic_loop(
            llm,
            ingestion_summary=state["ingestion_summary"],
            analysis_stats=state["stats"],
            max_iterations=8,
        )
    except Exception as e:
        print(f"[Root Cause Agent] Error: {e}")
        return {
            "error": f"Root cause analysis failed: {e}",
            "current_step": "root_cause",
            "progress": 60,
        }

    hi = [p for p in patterns if p.get("severity") in ("critical","high")]
    cs = [p for p in patterns if len(p.get("data_sources",[])) > 1]

    print(f"[Root Cause Agent] ✓ {len(patterns)} patterns | "
          f"{len(hi)} high/critical | {len(cs)} cross-source")

    return {
        "patterns": patterns,
        "pattern_stats": {
            "total":           len(patterns),
            "critical":        sum(1 for p in patterns if p.get("severity")=="critical"),
            "high":            sum(1 for p in patterns if p.get("severity")=="high"),
            "cross_source":    len(cs),
            "warehouses_flagged": len({w for p in patterns for w in p.get("warehouses",[])}),
        },
        "current_step": "root_cause",
        "progress": 65,
        "messages": [SystemMessage(
            content=f"Root cause analysis complete: {len(patterns)} patterns found via "
                    f"autonomous tool-calling. High/critical: {len(hi)}. "
                    f"Top: {patterns[0]['title'] if patterns else 'none'}"
        )],
    }