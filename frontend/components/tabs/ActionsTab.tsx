"use client";
import { ActionItem } from "../../lib/api";

const P_STYLE: Record<string,{chip:string;bar:string}> = {
  immediate:  { chip:"chip chip-danger", bar:"bg-[var(--danger)]" },
  this_week:  { chip:"chip chip-amber",  bar:"bg-[var(--amber)]" },
  this_month: { chip:"chip chip-muted",  bar:"bg-purple-500" },
};

function Section({ title, items, barColor }: { title:string; items:ActionItem[]; barColor:string }) {
  if (!items.length) return null;
  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <div className={`h-px flex-1 ${barColor} opacity-30`} />
        <span className="section-label">{title} — {items.length}</span>
        <div className={`h-px flex-1 ${barColor} opacity-30`} />
      </div>
      <div className="space-y-2">
        {items.map(a => (
          <div key={a.action_id} className="card p-4 flex gap-4 hover:border-[var(--amber)]/30 transition-colors">
            <div className="shrink-0 mono text-[10px] text-[var(--muted)] pt-0.5 w-10">{a.action_id}</div>
            <div className="flex-1 min-w-0">
              <div className="flex items-start gap-2 flex-wrap mb-1">
                <span className="display font-bold text-sm text-[var(--text)]">{a.title}</span>
                <span className={P_STYLE[a.priority]?.chip || "chip chip-muted"}>
                  {a.priority?.replace(/_/g," ")}
                </span>
              </div>
              <p className="mono text-[10px] text-[var(--muted)] leading-relaxed mb-2">{a.description}</p>
              <div className="flex flex-wrap gap-4 mono text-[10px]">
                <span className="text-[var(--muted)]">Owner: <span className="text-[var(--text)]">{a.owner}</span></span>
                <span className="text-[var(--muted)]">Deadline: <span className="text-[var(--text)]">{a.deadline_days}d</span></span>
                {a.pattern_ref && (
                  <span className="text-[var(--muted)]">Ref: <span className="text-[var(--amber)]">{a.pattern_ref}</span></span>
                )}
              </div>
              {a.kpi && (
                <p className="mono text-[9px] text-[var(--amber)]/70 mt-1.5">📈 Track: {a.kpi}</p>
              )}
              {a.estimated_impact && (
                <p className="mono text-[9px] text-[var(--ok)]/70 mt-0.5">→ {a.estimated_impact}</p>
              )}
            </div>
            <div className="shrink-0 text-right">
              <div className="display font-black text-2xl text-[var(--text)]">{a.deadline_days}</div>
              <div className="mono text-[9px] text-[var(--muted)]">DAYS</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ActionsTab({ actions }: { actions: ActionItem[] }) {
  if (!actions.length) return (
    <div className="flex items-center justify-center h-64 text-[var(--muted)] mono text-xs">
      No actions generated yet.
    </div>
  );
  const imm  = actions.filter(a => a.priority === "immediate");
  const week = actions.filter(a => a.priority === "this_week");
  const mon  = actions.filter(a => a.priority === "this_month");

  return (
    <div className="space-y-6 animate-fade-up">
      <div>
        <h2 className="display font-black text-xl text-[var(--text)]">Action Items</h2>
        <p className="mono text-[10px] text-[var(--muted)]">
          {imm.length} immediate · {week.length} this week · {mon.length} this month
        </p>
      </div>
      <Section title="IMMEDIATE ACTION REQUIRED" items={imm}  barColor="bg-[var(--danger)]" />
      <Section title="THIS WEEK"                 items={week} barColor="bg-[var(--amber)]" />
      <Section title="THIS MONTH"                items={mon}  barColor="bg-purple-500" />
    </div>
  );
}