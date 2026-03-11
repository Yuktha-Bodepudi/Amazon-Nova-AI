"use client";
import { PipelineStatus } from "../lib/api";

const NODES = [
  { id:"ingestion",  label:"INGESTION NODE",    sub:"4 sources → unified schema",                    sym:"⬇", tools:0 },
  { id:"analysis",   label:"ANALYSIS NODE",     sub:"Nova Lite · 200 records enriched",              sym:"◈", tools:0 },
  { id:"root_cause", label:"ROOT CAUSE NODE",   sub:"Nova Pro · autonomous tool-calling ReAct loop", sym:"⬡", tools:8 },
  { id:"action",     label:"ACTION NODE",       sub:"LangChain chains · 5 deliverables",             sym:"◆", tools:0 },
  { id:"voice",      label:"VOICE NODE",        sub:"Nova Sonic · message history loaded",           sym:"◎", tools:0 },
];

const TOOLS = ["load_shift_reports","load_safety_incidents","load_qc_failures",
               "load_customer_returns","find_product_overlap","compare_shift_risk",
               "get_warehouse_scorecard","get_category_quality_report"];

function nodeState(id:string, status:PipelineStatus): "done"|"active"|"pending" {
  const order = NODES.map(n=>n.id);
  const cur = order.indexOf(status.step||"");
  const idx = order.indexOf(id);
  if (status.complete)  return "done";
  if (idx < cur)        return "done";
  if (idx === cur)      return "active";
  return "pending";
}

export default function GraphOverlay({ status }: { status: PipelineStatus }) {
  return (
    <div className="flex items-center justify-center h-full p-8">
      <div className="flex gap-6 max-w-4xl w-full animate-fade-up">

        {/* Main graph */}
        <div className="card flex-1 p-6">
          <div className="flex items-end justify-between mb-6">
            <div>
              <p className="section-label mb-1">LangGraph Pipeline</p>
              <p className="display font-black text-xl text-[var(--text)]">{status.message || "Initializing..."}</p>
            </div>
            <div className="display font-black text-4xl text-[var(--amber)]">{status.progress}%</div>
          </div>
          <div className="h-0.5 bg-[var(--border)] mb-6 relative">
            <div className="absolute inset-y-0 left-0 bg-[var(--amber)] transition-all duration-700 h-0.5"
                 style={{width:`${status.progress}%`}} />
          </div>

          <div className="space-y-1">
            {NODES.map((node, i) => {
              const s = nodeState(node.id, status);
              return (
                <div key={node.id}>
                  <div className="flex items-center gap-3 py-2.5">
                    <div className={`w-9 h-9 flex items-center justify-center mono text-sm border shrink-0 transition-all
                      ${s==="done"  ?"border-[var(--ok)]/40 text-[var(--ok)] bg-[var(--ok)]/8":
                        s==="active"?"border-[var(--amber)] text-[var(--amber)] bg-[var(--amber)]/10 animate-pulse-amb":
                                     "border-[var(--border)] text-[var(--muted)]"}`}>
                      {s==="done" ? "✓" : node.sym}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className={`display font-bold text-sm transition-colors
                        ${s==="active"?"text-[var(--amber)]":s==="done"?"text-[var(--text)]":"text-[var(--muted)]"}`}>
                        {node.label}
                      </div>
                      <div className="mono text-[9px] text-[var(--muted)]">{node.sub}</div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {node.tools > 0 && (
                        <span className="chip chip-amber">{node.tools} TOOLS</span>
                      )}
                      {s==="active" && <span className="chip chip-amber">RUNNING</span>}
                      {s==="done"   && <span className="chip chip-ok">DONE</span>}
                    </div>
                  </div>
                  {i < NODES.length-1 && (
                    <div className={`ml-4 w-px h-3 ${s==="done"?"bg-[var(--ok)]/30":"bg-[var(--border)]"}`} />
                  )}
                </div>
              );
            })}
          </div>

          {status.complete && (
            <div className="mt-4 py-2.5 border border-[var(--ok)]/30 bg-[var(--ok)]/5 text-center">
              <span className="mono text-[10px] text-[var(--ok)] tracking-widest">✓ GRAPH EXECUTION COMPLETE</span>
            </div>
          )}
          {status.error && (
            <div className="mt-4 py-2.5 card-danger px-4">
              <p className="mono text-[10px] text-[var(--danger)]">✗ {status.error}</p>
            </div>
          )}
        </div>

        {/* Tool panel */}
        <div className="w-52 shrink-0 flex flex-col gap-3">
          <div className="card p-4">
            <p className="section-label mb-3">LangChain Tools</p>
            <p className="mono text-[9px] text-[var(--muted)] mb-3 leading-relaxed">
              Root Cause Agent autonomously decides which tools to call
            </p>
            <div className="space-y-1">
              {TOOLS.map(t => (
                <div key={t} className={`mono text-[9px] py-1 border-b border-[var(--border)] transition-colors
                  ${status.step==="root_cause" && status.running
                    ? "text-[var(--amber)] animate-pulse" : "text-[var(--muted)]"}`}>
                  {t}()
                </div>
              ))}
            </div>
          </div>
          <div className="card p-4">
            <p className="section-label mb-2">State Flow</p>
            <p className="mono text-[9px] text-[var(--muted)] leading-relaxed">
              Each node reads from WarehouseState and writes its outputs back.
              Messages accumulate via LangGraph add_messages reducer.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}