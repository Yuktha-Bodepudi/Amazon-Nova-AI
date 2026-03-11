"use client";
import { Tab } from "../app/page";

const AGENTS = [
  {name:"Ingestion",  role:"4 sources → schema"},
  {name:"Analysis",   role:"Nova Lite · sample"},
  {name:"Root Cause", role:"Nova Pro · tools"},
  {name:"Action",     role:"5 deliverables"},
  {name:"Voice",      role:"Nova Sonic"},
];

const TABS: {id:Tab;label:string;sym:string;key:string}[] = [
  {id:"overview", label:"OVERVIEW",  sym:"◈", key:""},
  {id:"patterns", label:"PATTERNS",  sym:"⬡", key:"patterns"},
  {id:"actions",  label:"ACTIONS",   sym:"◆", key:"action_items"},
  {id:"records",  label:"RECORDS",   sym:"▤", key:"records"},
  {id:"voice",    label:"VOICE AI",  sym:"◎", key:""},
];

export default function Sidebar({ tab, setTab, results }: {
  tab:Tab; setTab:(t:Tab)=>void; results:any;
}) {
  const cnt = (key:string) => {
    if (!results||!key) return null;
    const v = results[key]; return Array.isArray(v) ? v.length : null;
  };
  return (
    <aside className="w-48 shrink-0 border-r border-[var(--border)] bg-[var(--ink2)] flex flex-col">
      <div className="px-4 py-3 border-b border-[var(--border)]">
        <p className="section-label mb-2.5">LangGraph Nodes</p>
        {AGENTS.map(a => (
          <div key={a.name} className="flex items-center gap-2 mb-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${results?"bg-[var(--ok)]":"bg-[var(--border)]"}`} />
            <div>
              <span className="mono text-[9px] text-[var(--muted)]">{a.name}</span>
              <span className="mono text-[8px] text-[var(--muted)]/50 ml-1">{a.role}</span>
            </div>
          </div>
        ))}
      </div>
      <nav className="flex-1 py-2">
        {TABS.map(t => {
          const n = cnt(t.key);
          const active = tab===t.id;
          return (
            <button key={t.id} onClick={()=>setTab(t.id)}
              className={`w-full flex items-center justify-between px-4 py-2.5 border-l-2 transition-all group
                ${active?"bg-[var(--amber)]/10 border-[var(--amber)]":"border-transparent hover:bg-white/3"}`}>
              <div className="flex items-center gap-2.5">
                <span className={`mono text-sm ${active?"text-[var(--amber)]":"text-[var(--muted)]"}`}>{t.sym}</span>
                <span className={`display font-semibold text-xs tracking-wide ${active?"text-[var(--amber)]":"text-[var(--muted)]"}`}>{t.label}</span>
              </div>
              {n!==null && (
                <span className={`mono text-[9px] px-1.5 py-0.5 ${active?"bg-[var(--amber)]/20 text-[var(--amber)]":"bg-[var(--border)] text-[var(--muted)]"}`}>{n}</span>
              )}
            </button>
          );
        })}
      </nav>
      {results?.stats && (
        <div className="px-4 py-3 border-t border-[var(--border)]">
          <p className="section-label mb-2">Last Run</p>
          {[["Total",results.stats?.total_records],["Patterns",results.stats?.patterns?.total],
            ["Actions",results.stats?.actions?.total_actions],["Alerts",results.alerts?.length]]
            .filter(([,v])=>v!=null).map(([l,v])=>(
            <div key={l as string} className="flex justify-between py-0.5">
              <span className="mono text-[9px] text-[var(--muted)]">{l}</span>
              <span className="mono text-[9px] text-[var(--text)]">{(v as number).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}