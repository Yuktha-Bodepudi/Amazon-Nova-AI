"use client";
import { useState, useMemo } from "react";
import { Record_ } from "../../lib/api";

const TYPE_META: Record<string,{icon:string;color:string}> = {
  debrief:  { icon:"📋", color:"text-blue-400"   },
  safety:   { icon:"🦺", color:"text-red-400"    },
  qc:       { icon:"🔍", color:"text-yellow-400" },
  returns:  { icon:"↩",  color:"text-purple-400" },
  voice:    { icon:"🎙", color:"text-[var(--ok)]"},
};
const SENT_COLOR: Record<string,string> = {
  positive:"text-[var(--ok)]",negative:"text-[var(--danger)]",
  mixed:"text-[var(--amber)]",neutral:"text-[var(--muted)]"
};

export default function RecordsTab({ records }: { records: Record_[] }) {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  const types = useMemo(
  () => ["all", ...Array.from(new Set(records.map(r => r.source_type)))],
  [records]
);
  const counts = useMemo(() => {
    const c: Record<string,number> = {};
    records.forEach(r => { c[r.source_type] = (c[r.source_type]||0)+1; });
    return c;
  },[records]);

  const filtered = useMemo(() => records
    .filter(r => filter==="all" || r.source_type===filter)
    .filter(r => !search || r.text?.toLowerCase().includes(search.toLowerCase()) ||
                 r.warehouse_id?.includes(search.toUpperCase()) ||
                 r.zone?.includes(search.toUpperCase()))
    ,[records,filter,search]);

  if (!records.length) return (
    <div className="flex items-center justify-center h-64 text-[var(--muted)] mono text-xs">No records loaded.</div>
  );

  return (
    <div className="space-y-3 animate-fade-up">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <input value={search} onChange={e=>setSearch(e.target.value)}
          placeholder="Search records..."
          className="bg-[var(--ink2)] border border-[var(--border)] px-3 py-1.5 mono text-xs text-[var(--text)] placeholder-[var(--muted)] focus:outline-none focus:border-[var(--amber)] w-44"
        />
        <div className="flex gap-1 flex-wrap">
          {types.map(t => (
            <button key={t} onClick={()=>setFilter(t)}
              className={`mono text-[10px] px-2.5 py-1.5 border transition-colors
                ${filter===t
                  ? "border-[var(--amber)] bg-[var(--amber)]/10 text-[var(--amber)]"
                  : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)]"
                }`}>
              {t==="all" ? `ALL (${records.length})` : `${TYPE_META[t]?.icon||""} ${t} (${counts[t]||0})`}
            </button>
          ))}
        </div>
        <span className="mono text-[9px] text-[var(--muted)] ml-auto">{filtered.length} shown</span>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
        {filtered.slice(0,100).map(r => {
          const m  = TYPE_META[r.source_type] || {icon:"·",color:""};
          const ai = r.analysis;
          return (
            <div key={r.id} className={`card p-3 hover:border-[var(--amber)]/20 transition-colors`}>
              {/* Header */}
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="mono text-[9px] text-[var(--muted)]">{r.id}</span>
                  <span className={`chip ${m.color} border border-current/20 bg-current/5`}>
                    {m.icon} {r.source_type}
                  </span>
                  {r.severity === "high" && <span className="chip chip-danger">HIGH</span>}
                </div>
                <span className={`mono text-[9px] ${SENT_COLOR[ai?.sentiment||""]||"text-[var(--muted)]"}`}>
                  {ai?.sentiment || ""}
                </span>
              </div>

              {/* Meta */}
              <div className="flex gap-2 mb-1.5 flex-wrap">
                <span className="mono text-[9px] text-[var(--muted)]">{r.date}</span>
                {r.warehouse_id && <span className="chip chip-muted">{r.warehouse_id}</span>}
                {r.zone         && <span className="chip chip-muted">Zone {r.zone}</span>}
                {r.shift        && <span className="chip chip-muted">{r.shift}</span>}
              </div>

              {/* Text */}
              <p className="mono text-[10px] text-[var(--muted)] leading-relaxed line-clamp-2">{r.text}</p>

              {/* AI summary */}
              {ai?.summary && (
                <p className="mono text-[9px] text-[var(--amber)]/70 mt-1.5 italic line-clamp-1">
                  → {ai.summary}
                </p>
              )}

              {/* Tags */}
              {r.tags?.length > 0 && (
                <div className="flex gap-1 mt-2 flex-wrap">
                  {r.tags.filter(Boolean).slice(0,4).map(t => (
                    <span key={t} className="chip chip-muted">{t}</span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {filtered.length > 100 && (
        <p className="mono text-[10px] text-[var(--muted)] text-center">
          Showing 100 of {filtered.length} records
        </p>
      )}
    </div>
  );
}