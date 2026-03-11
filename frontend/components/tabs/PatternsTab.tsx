"use client";
import { useState } from "react";
import { Pattern } from "../../lib/api";

const SRC_ICON: Record<string,string> = {
  debrief:"📋", safety:"🦺", qc:"🔍", returns:"↩", voice:"🎙"
};
const SEV: Record<string,{border:string;bg:string;text:string;dot:string}> = {
  critical: { border:"border-red-500/50",    bg:"bg-red-500/5",    text:"text-red-400",    dot:"bg-red-500"    },
  high:     { border:"border-orange-500/50", bg:"bg-orange-500/5", text:"text-orange-400", dot:"bg-orange-500" },
  medium:   { border:"border-yellow-500/40", bg:"bg-yellow-500/5", text:"text-yellow-400", dot:"bg-yellow-500" },
  low:      { border:"border-green-500/30",  bg:"bg-green-500/5",  text:"text-green-400",  dot:"bg-green-500"  },
};
const URGENCY_CHIP: Record<string,string> = {
  immediate:"chip chip-danger", this_week:"chip chip-amber", this_month:"chip chip-muted"
};

export default function PatternsTab({ patterns }: { patterns: Pattern[] }) {
  const [open, setOpen] = useState<string|null>(null);
  if (!patterns.length) return (
    <div className="flex items-center justify-center h-64 text-[var(--muted)] mono text-xs">
      No patterns detected. Run the pipeline first.
    </div>
  );

  const sorted = [...patterns].sort((a,b) => {
    const o = {critical:0,high:1,medium:2,low:3};
    return (o[a.severity]||3)-(o[b.severity]||3);
  });

  const counts = {
    critical: patterns.filter(p=>p.severity==="critical").length,
    high:     patterns.filter(p=>p.severity==="high").length,
    medium:   patterns.filter(p=>p.severity==="medium").length,
    low:      patterns.filter(p=>p.severity==="low").length,
  };

  return (
    <div className="space-y-3 animate-fade-up">
      {/* Header */}
      <div className="flex items-end justify-between mb-1">
        <div>
          <h2 className="display font-black text-xl text-[var(--text)]">Root Cause Patterns</h2>
          <p className="mono text-[10px] text-[var(--muted)] mt-0.5">
            Cross-source intelligence — shift reports · safety · QC · returns
          </p>
        </div>
        <div className="flex gap-2">
          {Object.entries(counts).filter(([,v])=>v>0).map(([sev,n]) => (
            <span key={sev} className={`chip ${SEV[sev]?.text || ""} border ${SEV[sev]?.border || ""} ${SEV[sev]?.bg || ""}`}>
              {n} {sev}
            </span>
          ))}
        </div>
      </div>

      {sorted.map(p => {
        const s = SEV[p.severity] || SEV.low;
        const isOpen = open === p.pattern_id;
        return (
          <div key={p.pattern_id}
            className={`border transition-all cursor-pointer ${s.border} ${s.bg}`}
            onClick={() => setOpen(isOpen ? null : p.pattern_id)}
          >
            {/* Row */}
            <div className="flex items-start gap-3 p-4">
              <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${s.dot}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div>
                    <span className="mono text-[9px] text-[var(--muted)] mr-2">{p.pattern_id}</span>
                    <span className={`display font-bold text-base ${s.text}`}>{p.title}</span>
                  </div>
                  <span className="mono text-[var(--muted)] text-xs shrink-0">{isOpen ? "▲" : "▼"}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {p.warehouses?.map(w => <span key={w} className="chip chip-muted">{w}</span>)}
                  {p.shifts_affected && p.shifts_affected !== "All" && (
                    <span className="chip chip-muted">{p.shifts_affected}</span>
                  )}
                  {p.data_sources?.map(src => (
                    <span key={src} className="chip chip-muted">{SRC_ICON[src]||"·"} {src}</span>
                  ))}
                  <span className="chip chip-muted">{p.occurrence_count}× detected</span>
                </div>
              </div>
            </div>

            {/* Expanded */}
            {isOpen && (
              <div className="border-t border-white/5 p-4 space-y-4 animate-fade-up">
                <div>
                  <p className="section-label mb-1">Pattern</p>
                  <p className="mono text-xs text-[var(--text)] leading-relaxed">{p.description}</p>
                </div>
                <div>
                  <p className="section-label mb-1">Root Cause</p>
                  <p className="mono text-xs text-[var(--text)] leading-relaxed">{p.root_cause}</p>
                </div>
                {p.evidence?.length > 0 && (
                  <div>
                    <p className="section-label mb-2">Evidence</p>
                    <div className="space-y-1">
                      {p.evidence.map((e,i) => (
                        <div key={i} className="flex gap-2">
                          <span className={`${s.text} mono text-xs shrink-0`}>›</span>
                          <span className="mono text-xs text-[var(--muted)]">{e}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div>
                  <p className="section-label mb-2">Recommended Actions</p>
                  <div className="space-y-2">
                    {p.actions?.map((a,i) => (
                      <div key={i} className="flex items-start gap-3 p-3 bg-black/20 border border-[var(--border)]">
                        <span className={URGENCY_CHIP[a.urgency] || "chip chip-muted"}>
                          {a.urgency?.replace("_"," ")}
                        </span>
                        <div className="flex-1">
                          <p className="mono text-xs text-[var(--text)]">{a.action}</p>
                          <p className="mono text-[10px] text-[var(--muted)] mt-0.5">Owner: {a.owner}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="p-3 border border-[var(--ok)]/25 bg-[var(--ok)]/5">
                  <span className="mono text-[10px] text-[var(--ok)]">IMPACT: </span>
                  <span className="mono text-[10px] text-[var(--text)]">{p.impact}</span>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}