"use client";
import { PipelineStatus } from "../lib/api";

export default function Header({ status, onRun, loading, alertCount ,canRun }: {
  status:PipelineStatus; onRun:()=>void; loading:boolean; alertCount:number; canRun: boolean; 
}) {
  return (
    <header className="shrink-0 border-b border-[var(--border)] bg-[var(--ink2)] px-5 h-12 flex items-center justify-between z-10">
      <div className="flex items-center gap-4">
        <div className="flex items-baseline gap-0.5">
          <span className="display font-black text-lg text-[var(--amber)]">WAREHOUSE</span>
          <span className="display font-black text-lg text-[var(--text)]">IQ</span>
          <span className="text-[var(--amber)] animate-blink ml-1">_</span>
        </div>
        <div className="h-4 w-px bg-[var(--border)]" />
        <span className="chip chip-amber">LANGGRAPH</span>
        <span className="mono text-[9px] text-[var(--muted)] tracking-widest">5-AGENT AGENTIC SYSTEM</span>
      </div>

      {status.running && (
        <div className="flex items-center gap-3 flex-1 mx-8 max-w-md">
          <span className="mono text-[9px] text-[var(--muted)] truncate">{status.message}</span>
          <div className="flex-1 h-0.5 bg-[var(--border)] relative">
            <div className="absolute inset-y-0 left-0 bg-[var(--amber)] transition-all duration-500"
                 style={{width:`${status.progress}%`}} />
          </div>
          <span className="mono text-[10px] text-[var(--amber)] w-8 text-right">{status.progress}%</span>
        </div>
      )}

      <div className="flex items-center gap-3">
        {alertCount > 0 && (
          <div className="chip chip-danger animate-pulse-amb">⚠ {alertCount} ALERT{alertCount>1?"S":""}</div>
        )}
        <button onClick={onRun} disabled={loading || !canRun} className="btn-primary flex items-center gap-2">
          {loading ? <><span className="animate-spin inline-block">⟳</span> {status.progress}%</> : "▶  RUN PIPELINE"}
        </button>
      </div>
    </header>
  );
}