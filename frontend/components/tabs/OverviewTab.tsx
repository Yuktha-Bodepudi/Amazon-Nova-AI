"use client";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer, RadarChart, Radar, PolarGrid, PolarAngleAxis } from "recharts";

const T = { style: { fill: "var(--muted)", fontSize: 9, fontFamily: "JetBrains Mono" } };
const TOOLTIP_STYLE = { background:"#111110", border:"1px solid #2A2A22", borderRadius:0, fontSize:10, fontFamily:"JetBrains Mono" };

function Stat({ label, value, sub, accent }: { label:string; value:any; sub?:string; accent?:string }) {
  return (
    <div className="card p-4">
      <p className="section-label mb-1">{label}</p>
      <div className={`display font-black text-3xl ${accent || "text-[var(--text)]"}`}>
        {value?.toLocaleString() ?? "—"}
      </div>
      {sub && <p className="mono text-[10px] text-[var(--muted)] mt-0.5">{sub}</p>}
    </div>
  );
}

export default function OverviewTab({ results }: { results: any }) {
  const s     = results?.stats || {};
  const safety  = s.safety  || {};
  const qc      = s.qc      || {};
  const returns = s.returns || {};
  const debrief = s.debriefs || {};
  const ai      = s.ai      || {};
  const alerts  = results?.alerts || [];
  const trend   = results?.trend_report || "";
  const briefing= results?.voice_briefing || "";

  // Bar chart data
  const warehouseData = Object.entries(safety.by_warehouse || {}).map(([wh, cnt]) => ({
    wh, injuries: cnt as number,
    qc_fail: qc.fail_by_warehouse?.[wh] || 0,
  }));

  const equipData = Object.entries(safety.by_equipment || {}).map(([eq, cnt]) => ({
    name: eq.split(" ").map((w:string) => w[0]).join(""), full: eq, value: cnt as number
  }));

  const defectData = Object.entries(qc.by_defect_type || {}).slice(0,6).map(([k,v]) => ({
    name: k.replace(" ","_"), value: v as number
  }));

  const sentData = Object.entries(ai.sentiment || {}).map(([k,v]) => ({
    name: k, value: v as number,
    fill: k==="negative"?"#EF4444":k==="positive"?"#22C55E":k==="mixed"?"#F59E0B":"#6B6860"
  }));

  const themeData = (ai.top_themes || []).slice(0,6).map(([t,v]: [string,number]) => ({
    theme: t.replace(/_/g," "), value: v
  }));

  return (
    <div className="space-y-4 animate-fade-up">
      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="space-y-2">
          {alerts.map((a:any) => (
            <div key={a.alert_id} className="card-danger px-4 py-3 flex items-start gap-4">
              <span className="text-xl mt-0.5">{a.emoji}</span>
              <div className="flex-1">
                <p className="display font-bold text-sm text-[var(--danger)]">{a.title}</p>
                <p className="mono text-[10px] text-[var(--muted)] mt-0.5 line-clamp-2">{a.summary}</p>
                <div className="flex gap-2 mt-1.5 flex-wrap">
                  {a.warehouses?.map((w:string) => <span key={w} className="chip chip-danger">{w}</span>)}
                  {a.sources?.map((s:string)  => <span key={s} className="chip chip-muted">{s}</span>)}
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="display font-black text-2xl text-[var(--danger)]">{a.occurrences}</div>
                <div className="mono text-[9px] text-[var(--muted)]">OCCURRENCES</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Top stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Total Records"     value={s.total_records}          />
        <Stat label="Safety Injuries"   value={safety.injuries}          accent="text-[var(--danger)]" sub={`${safety.total_days_lost} days lost`} />
        <Stat label="QC Fail Rate"      value={`${qc.fail_rate_pct}%`}   accent="text-[var(--amber)]"  sub={`${qc.failures} of ${qc.total}`} />
        <Stat label="Defect Returns"    value={`${returns.defect_rate_pct}%`} accent="text-[var(--amber)]" sub={`${returns.defect_related} of ${returns.total}`} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Night Injuries"    value={safety.night_injuries}    accent="text-orange-400"     sub="vs night shift" />
        <Stat label="Root Causes Found" value={s.patterns?.total}        accent="text-[var(--amber)]" />
        <Stat label="Immediate Actions" value={s.actions?.immediate}     accent="text-[var(--danger)]"sub="need action now" />
        <Stat label="Staffing→Picking"  value={debrief.staffing_AND_picking} accent="text-purple-400" sub="co-occurrence in debriefs" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Warehouse comparison */}
        <div className="card p-4 col-span-1">
          <p className="section-label mb-3">Injuries by Warehouse</p>
          <ResponsiveContainer width="100%" height={130}>
            <BarChart data={warehouseData} barSize={16}>
              <XAxis dataKey="wh" tick={T} axisLine={false} tickLine={false} />
              <YAxis hide />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="injuries" fill="var(--danger)" radius={[1,1,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* QC defect types */}
        <div className="card p-4 col-span-1">
          <p className="section-label mb-3">QC Defect Types</p>
          <ResponsiveContainer width="100%" height={130}>
            <BarChart data={defectData} barSize={14}>
              <XAxis dataKey="name" tick={{...T, fontSize:7}} axisLine={false} tickLine={false} />
              <YAxis hide />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="value" radius={[1,1,0,0]}>
                {defectData.map((_,i) => <Cell key={i} fill={i===0?"var(--amber)":"var(--amber-dim)"} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Sentiment */}
        <div className="card p-4 col-span-1">
          <p className="section-label mb-3">AI Sentiment (Sample)</p>
          <ResponsiveContainer width="100%" height={130}>
            <BarChart data={sentData} barSize={22}>
              <XAxis dataKey="name" tick={T} axisLine={false} tickLine={false} />
              <YAxis hide />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="value" radius={[1,1,0,0]}>
                {sentData.map((d,i) => <Cell key={i} fill={d.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Second charts row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Equipment injuries */}
        {equipData.length > 0 && (
          <div className="card p-4">
            <p className="section-label mb-3">Injuries by Equipment</p>
            <div className="space-y-2">
              {equipData.sort((a,b)=>b.value-a.value).map((d, i) => (
                <div key={d.full} className="flex items-center gap-3">
                  <span className="mono text-[10px] text-[var(--muted)] w-28 truncate">{d.full}</span>
                  <div className="flex-1 h-1.5 bg-[var(--border)] relative">
                    <div className="absolute inset-y-0 left-0 bg-[var(--danger)] transition-all"
                         style={{ width:`${(d.value/equipData[0].value)*100}%` }} />
                  </div>
                  <span className="mono text-[10px] text-[var(--text)] w-6 text-right">{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Debrief issue categories */}
        <div className="card p-4">
          <p className="section-label mb-3">Debrief Issue Categories</p>
          <div className="space-y-2">
            {Object.entries(debrief.issue_categories || {}).sort(([,a],[,b])=>(b as number)-(a as number)).map(([cat, cnt]) => {
              const max = Math.max(...Object.values(debrief.issue_categories || {}) as number[]);
              return (
                <div key={cat} className="flex items-center gap-3">
                  <span className="mono text-[10px] text-[var(--muted)] w-28">{cat}</span>
                  <div className="flex-1 h-1.5 bg-[var(--border)] relative">
                    <div className="absolute inset-y-0 left-0 bg-[var(--amber)] transition-all"
                         style={{ width:`${((cnt as number)/max)*100}%` }} />
                  </div>
                  <span className="mono text-[10px] text-[var(--text)] w-6 text-right">{cnt as number}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Voice briefing */}
      {briefing && (
        <div className="card-amber p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[var(--amber)]">◎</span>
            <p className="section-label text-[var(--amber)]">Voice Briefing · Nova Sonic Ready</p>
          </div>
          <p className="mono text-xs text-[var(--text)] italic leading-relaxed">{briefing}</p>
        </div>
      )}

      {/* Trend report */}
      {trend && (
        <div className="card p-5">
          <p className="section-label mb-3">Weekly Trend Report</p>
          <p className="mono text-xs text-[var(--text)] leading-relaxed">{trend}</p>
        </div>
      )}
    </div>
  );
}