"use client";
import { useState, useRef, useEffect } from "react";
import { api } from "../../lib/api";

type Msg = { role:"user"|"ai"; text:string; ts:string };

const QUICK = [
  "What is the single biggest safety risk right now?",
  "Which warehouse has the most problems?",
  "What should I fix first tomorrow morning?",
  "Why are there so many QC failures?",
  "How does night shift compare to day shift for injuries?",
  "Which products have both QC failures and returns?",
];

export default function VoiceTab({ results }: { results: any }) {
  const [msgs,      setMsgs]      = useState<Msg[]>([]);
  const [input,     setInput]     = useState("");
  const [loading,   setLoading]   = useState(false);
  const [recording, setRecording] = useState(false);
  const [recorder,  setRecorder]  = useState<MediaRecorder|null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const briefing  = results?.voice_briefing || "";
  const stats     = results?.stats || {};
  const patterns  = results?.patterns || [];

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:"smooth" }); }, [msgs]);

  const addMsg = (role:"user"|"ai", text:string) =>
    setMsgs(m => [...m, { role, text, ts: new Date().toLocaleTimeString() }]);

  const sendText = async () => {
    if (!input.trim() || loading) return;
    const q = input.trim(); setInput(""); setLoading(true);
    addMsg("user", q);
    try {
      const r = await api.query(q);
      addMsg("ai", r.answer || "No response.");
    } catch { addMsg("ai", "Error connecting to API."); }
    setLoading(false);
  };

  const startRec = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio:true });
      const mr = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      mr.ondataavailable = e => chunks.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach(t=>t.stop());
        const blob = new Blob(chunks, {type:"audio/webm"});
        await sendAudio(blob);
      };
      mr.start(); setRecorder(mr); setRecording(true);
    } catch { addMsg("ai","Microphone denied. Use text input below."); }
  };

  const stopRec = () => { recorder?.stop(); setRecording(false); };

  const sendAudio = async (blob: Blob) => {
    setLoading(true); addMsg("user","🎙 [Voice query]");
    try {
      const r = await api.voiceAudio(blob);
      if (r.transcript && !r.transcript.includes("unavailable")) {
        setMsgs(m => { const c=[...m]; c[c.length-1].text=`🎙 "${r.transcript}"`; return c; });
      }
      addMsg("ai", r.response_text || "No response.");
    } catch { addMsg("ai","Voice processing failed. Try text input."); }
    setLoading(false);
  };

  return (
    <div className="h-[calc(100vh-112px)] flex gap-4 animate-fade-up">
      {/* Chat panel */}
      <div className="flex-1 flex flex-col card overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <span className="text-[var(--amber)]">◎</span>
            <div>
              <p className="display font-bold text-sm text-[var(--text)]">Voice AI Interface</p>
              <p className="mono text-[9px] text-[var(--muted)]">Amazon Nova Sonic · hands-free supervisor Q&A</p>
            </div>
          </div>
          <button onClick={() => { setMsgs([]); api.resetVoice(); }}
            className="mono text-[10px] text-[var(--muted)] hover:text-[var(--text)] transition-colors">
            CLEAR
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {msgs.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
              <span className="text-4xl text-[var(--amber)] animate-pulse-amb">◎</span>
              <p className="mono text-xs text-[var(--muted)]">Hold the button to speak, or type below</p>
              <p className="mono text-[10px] text-[var(--muted)]/60">Powered by Amazon Nova Sonic</p>
            </div>
          )}
          {msgs.map((m,i) => (
            <div key={i} className={`flex ${m.role==="user"?"justify-end":"justify-start"} animate-slide-in`}>
              <div className={`max-w-sm mono text-xs px-3.5 py-2.5 border
                ${m.role==="user"
                  ? "bg-[var(--amber)]/10 border-[var(--amber)]/25 text-[var(--amber)]"
                  : "bg-[var(--ink3)] border-[var(--border)] text-[var(--text)]"}`}>
                <p className="leading-relaxed">{m.text}</p>
                <p className={`text-[9px] mt-1 ${m.role==="user"?"text-[var(--amber)]/40":"text-[var(--muted)]/50"}`}>
                  {m.ts}
                </p>
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-[var(--ink3)] border border-[var(--border)] mono text-xs px-3.5 py-2.5 text-[var(--muted)]">
                <span className="animate-pulse">Processing...</span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Controls */}
        <div className="border-t border-[var(--border)] p-3 space-y-2">
          {/* PTT button */}
          <div className="flex justify-center">
            <button
              onMouseDown={startRec} onMouseUp={stopRec}
              onTouchStart={startRec} onTouchEnd={stopRec}
              className={`flex items-center gap-2 px-8 py-3 display font-bold text-sm tracking-wide uppercase select-none transition-all
                ${recording
                  ? "bg-[var(--danger)] text-white scale-105 glow-danger"
                  : "bg-[var(--amber)]/15 text-[var(--amber)] border border-[var(--amber)]/30 hover:bg-[var(--amber)]/25"
                }`}>
              {recording ? <><span className="animate-pulse">●</span> RECORDING</> : <>◎ HOLD TO SPEAK</>}
            </button>
          </div>
          {/* Text input */}
          <div className="flex gap-2">
            <input value={input} onChange={e=>setInput(e.target.value)}
              onKeyDown={e=>e.key==="Enter"&&sendText()}
              placeholder="Or type your question..."
              className="flex-1 bg-[var(--ink)] border border-[var(--border)] px-3 py-1.5 mono text-xs text-[var(--text)] placeholder-[var(--muted)] focus:outline-none focus:border-[var(--amber)]"
            />
            <button onClick={sendText} disabled={loading}
              className="btn-primary text-[11px] px-3">SEND</button>
          </div>
        </div>
      </div>

      {/* Right panel */}
      <div className="w-60 shrink-0 flex flex-col gap-3">
        {/* Briefing */}
        {briefing && (
          <div className="card-amber p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[var(--amber)]">◎</span>
              <p className="section-label text-[var(--amber)]">Briefing</p>
            </div>
            <p className="mono text-[10px] text-[var(--text)] leading-relaxed italic">{briefing}</p>
            <button onClick={() => addMsg("ai", briefing)}
              className="mt-2 w-full mono text-[10px] text-[var(--amber)] border border-[var(--amber)]/20 py-1.5 hover:bg-[var(--amber)]/10 transition-colors">
              READ IN CHAT
            </button>
          </div>
        )}

        {/* Quick questions */}
        <div className="card p-4 flex-1">
          <p className="section-label mb-3">Quick Questions</p>
          <div className="space-y-1">
            {QUICK.map(q => (
              <button key={q} onClick={()=>setInput(q)}
                className="w-full text-left mono text-[10px] text-[var(--muted)] hover:text-[var(--text)] p-2 hover:bg-white/3 transition-colors leading-relaxed border-b border-[var(--border)] last:border-0">
                {q}
              </button>
            ))}
          </div>
        </div>

        {/* Model info */}
        <div className="card p-4">
          <p className="section-label mb-2">Models Active</p>
          {[
            ["Nova Sonic",  "speech I/O",   "var(--amber)"],
            ["Nova Pro",    "reasoning",    "var(--ok)"],
            ["Nova Lite",   "enrichment",   "var(--ok)"],
          ].map(([m,r,c]) => (
            <div key={m} className="flex justify-between py-1">
              <span className="mono text-[10px] text-[var(--muted)]">{m}</span>
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full" style={{background:`var(${c.slice(4,-1)})`}} />
                <span className="mono text-[10px]" style={{color:`var(${c.slice(4,-1)})`}}>{r}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Live stats */}
        <div className="card p-4">
          <p className="section-label mb-2">Dataset</p>
          {[
            ["Debriefs",  stats.debriefs?.total],
            ["Safety",    stats.safety?.total],
            ["QC",        stats.qc?.total],
            ["Returns",   stats.returns?.total],
          ].map(([l,v]) => v && (
            <div key={l as string} className="flex justify-between py-0.5">
              <span className="mono text-[10px] text-[var(--muted)]">{l}</span>
              <span className="mono text-[10px] text-[var(--text)]">{(v as number).toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}