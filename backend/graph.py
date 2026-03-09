"""
WarehouseIQ — LangGraph Pipeline Definition

This is the core of the agentic system. The graph defines:
  - NODES:  each agent as a callable node
  - EDGES:  how state flows between agents  
  - CONDITIONAL EDGES: route to error handler if any agent fails

Graph structure:
  START
    │
    ▼
  ingestion_node  ──(error?)──► error_node ──► END
    │
    ▼
  analysis_node   ──(error?)──► error_node
    │
    ▼
  root_cause_node ──(error?)──► error_node  ← AGENTIC: tool-calling loop
    │
    ▼
  action_node     ──(error?)──► error_node
    │
    ▼
  voice_node
    │
    ▼
  END

Usage:
    graph = build_graph()
    result = graph.invoke(initial_state)        # synchronous
    # or
    for chunk in graph.stream(initial_state):   # streaming with progress
        print(chunk)
"""

import uuid
from datetime import datetime
from langgraph.graph import StateGraph, START, END
from state import WarehouseState
from agents.ingestion_agent  import ingestion_node
from agents.analysis_agent   import analysis_node
from agents.root_cause_agent import root_cause_node
from agents.action_agent     import action_node
from agents.voice_agent      import voice_node


# ── Error handler node ─────────────────────────────────────────────────────────

def error_node(state: WarehouseState) -> dict:
    """Catch-all error handler — logs and terminates gracefully."""
    err = state.get("error","Unknown error")
    print(f"\n[Graph] ✗ Error in {state.get('current_step','?')}: {err}")
    return {
        "complete":     True,
        "current_step": "error",
        "progress":     0,
    }


# ── Conditional edge functions ─────────────────────────────────────────────────

def route_after_ingestion(state: WarehouseState) -> str:
    if state.get("error"):
        return "error"
    if not state.get("raw_records"):
        return "error"
    return "analysis"


def route_after_analysis(state: WarehouseState) -> str:
    if state.get("error"):
        return "error"
    if not state.get("enriched_records"):
        return "error"
    return "root_cause"


def route_after_root_cause(state: WarehouseState) -> str:
    if state.get("error"):
        return "error"
    if not state.get("patterns"):
        return "error"
    return "action"


def route_after_action(state: WarehouseState) -> str:
    if state.get("error"):
        return "error"
    return "voice"


# ── Graph builder ──────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Builds and compiles the WarehouseIQ LangGraph.
    Returns a compiled graph ready to invoke or stream.
    """
    builder = StateGraph(WarehouseState)

    # Register nodes
    builder.add_node("ingestion",  ingestion_node)
    builder.add_node("analysis",   analysis_node)
    builder.add_node("root_cause", root_cause_node)
    builder.add_node("action",     action_node)
    builder.add_node("voice",      voice_node)
    builder.add_node("error",      error_node)

    # Entry point
    builder.add_edge(START, "ingestion")

    # Conditional edges (check for errors after each node)
    builder.add_conditional_edges("ingestion",  route_after_ingestion,
                                  {"analysis": "analysis", "error": "error"})
    builder.add_conditional_edges("analysis",   route_after_analysis,
                                  {"root_cause": "root_cause", "error": "error"})
    builder.add_conditional_edges("root_cause", route_after_root_cause,
                                  {"action": "action", "error": "error"})
    builder.add_conditional_edges("action",     route_after_action,
                                  {"voice": "voice", "error": "error"})

    # Terminal edges
    builder.add_edge("voice", END)
    builder.add_edge("error", END)

    return builder.compile()


def initial_state(run_id: str | None = None) -> WarehouseState:
    """Return the initial (empty) state to start a pipeline run."""
    return WarehouseState(
        run_id       = run_id or str(uuid.uuid4()),
        facility     = "FC Riverside Network",
        raw_records     = [],
        ingestion_summary = {},
        enriched_records  = [],
        stats           = {},
        patterns        = [],
        pattern_stats   = {},
        action_items    = [],
        alerts          = [],
        trend_report    = "",
        voice_briefing  = "",
        incident_report = None,
        messages        = [],
        current_step    = "starting",
        error           = None,
        complete        = False,
        progress        = 0,
    )


# ── Standalone runner ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json as j
    graph = build_graph()
    print("[Graph] Running pipeline...")
    result = graph.invoke(initial_state())
    print(f"\n[Graph] Complete: {result['complete']}")
    print(f"Patterns: {len(result.get('patterns',[]))}")
    print(f"Actions:  {len(result.get('action_items',[]))}")
    print(j.dumps(result.get("pattern_stats",{}), indent=2))