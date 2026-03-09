"""
WarehouseIQ — LangGraph State
This TypedDict is the single shared state object that flows through
every node in the graph. Agents read from it and write their outputs back.

LangGraph passes this state immutably between nodes — each node returns
a PARTIAL dict with only the keys it wants to update.
"""

from typing import TypedDict, Annotated, Any
from langgraph.graph.message import add_messages


class WarehouseState(TypedDict):
    """
    Shared state flowing through all 5 agent nodes in the LangGraph pipeline.
    Each field is written by exactly one agent and read by downstream agents.
    """

    # ── Set by caller ──────────────────────────────────────────────────────────
    run_id:         str          # unique pipeline run identifier
    facility:       str          # "FC Riverside Network"

    # ── Ingestion Agent output ─────────────────────────────────────────────────
    raw_records:    list[dict]   # 4000 unified records from 4 sources
    ingestion_summary: dict      # {total, by_type, by_warehouse, by_severity}

    # ── Analysis Agent output ──────────────────────────────────────────────────
    enriched_records: list[dict] # records with .analysis{} field on sampled 200
    stats:           dict        # full raw stats + ai sample stats

    # ── Root Cause Agent output ────────────────────────────────────────────────
    patterns:        list[dict]  # 5-6 cross-source root cause patterns
    pattern_stats:   dict        # {total, critical, high, cross_source}

    # ── Action Agent output ────────────────────────────────────────────────────
    action_items:    list[dict]  # ranked immediate/this_week/this_month
    alerts:          list[dict]  # slack-style alerts for critical/high
    trend_report:    str         # executive weekly trend summary
    voice_briefing:  str         # ≤55 words for Nova Sonic readback
    incident_report: str | None  # OSHA-style for worst pattern

    # ── Voice Agent output ─────────────────────────────────────────────────────
    # Messages accumulate via add_messages reducer (multi-turn conversation)
    messages: Annotated[list, add_messages]

    # ── Routing / control flow ─────────────────────────────────────────────────
    current_step:   str          # tracks which node just ran
    error:          str | None   # if set, graph routes to error handler
    complete:       bool         # True when pipeline finishes
    progress:       int          # 0-100 for frontend progress bar