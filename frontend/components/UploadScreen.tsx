"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../lib/api";

// ── The 4 required structured data files ──────────────────────────────────────
const FILE_SLOTS = [
  {
    key:      "debriefs",
    label:    "Shift Debrief Reports",
    filename: "synthetic_debriefs_1000.json",
    format:   "JSON",
    icon:     "📋",
    hint:     "date · shift · zone · summary · issues[]",
  },
  {
    key:      "safety",
    label:    "Safety Incident Logs",
    filename: "amazon_warehouse_safety_logs.json",
    format:   "JSON",
    icon:     "🦺",
    hint:     "log_id · warehouse_id · event_type · severity",
  },
  {
    key:      "qc",
    label:    "QC Inspection Flags",
    filename: "amazon_warehouse_qc_flags.csv",
    format:   "CSV",
    icon:     "🔍",
    hint:     "qc_id · warehouse_id · defect_type · qc_status",
  },
  {
    key:      "returns",
    label:    "Customer Returns",
    filename: "amazon_synthetic_returns.csv",
    format:   "CSV",
    icon:     "↩",
    hint:     "order_id · product_id · return_reason · condition",
  },
];

const AUDIO_FORMATS = [".mp3", ".wav", ".m4a", ".webm", ".flac", ".ogg", ".aac"];

type SlotState = {
  uploaded:  boolean;
  size_kb:   number;
  uploading: boolean;
  error:     string | null;
  dragOver:  boolean;
};

type VoiceMemo = {
  filename: string;
  size_kb:  number;
};

export default function UploadScreen({
  onAllReady,
  onRun,
  loading,
}: {
  onAllReady: (ready: boolean) => void;
  onRun: () => void;
  loading: boolean;
}) {
  const [slots, setSlots] = useState<Record<string, SlotState>>(
    Object.fromEntries(
      FILE_SLOTS.map(f => [f.key, { uploaded:false, size_kb:0, uploading:false, error:null, dragOver:false }])
    )
  );
  const [voiceMemos,    setVoiceMemos]    = useState<VoiceMemo[]>([]);
  const [voiceUploading, setVoiceUploading] = useState(false);
  const [voiceDragOver,  setVoiceDragOver]  = useState(false);
  const [voiceError,     setVoiceError]     = useState<string | null>(null);

  const fileInputRefs  = useRef<Record<string, HTMLInputElement | null>>({});
  const voiceInputRef  = useRef<HTMLInputElement | null>(null);

  // ── Sync with backend on mount ─────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const s = await api.getUploadStatus();
        if (!s?.files) return;
        setSlots(prev => {
          const next = { ...prev };
          for (const [key, info] of Object.entries(s.files as Record<string, any>)) {
            if (info.uploaded) {
              next[key] = { ...next[key], uploaded:true, size_kb:info.size_kb, error:null };
            }
          }
          return next;
        });
        if (s.voicememos?.files) setVoiceMemos(s.voicememos.files);
        onAllReady(s.all_ready);
      } catch {}
    })();
  }, [onAllReady]);

  const allUploaded = FILE_SLOTS.every(f => slots[f.key]?.uploaded);

  // ── Structured file upload ─────────────────────────────────────────────────
  const uploadFile = useCallback(async (key: string, file: File) => {
    setSlots(prev => ({ ...prev, [key]: { ...prev[key], uploading:true, error:null } }));
    try {
      const result = await api.uploadFile(key, file);
      setSlots(prev => {
        const next = {
          ...prev,
          [key]: { ...prev[key], uploading:false, uploaded:true, size_kb:result.size_kb, error:null }
        };
        onAllReady(FILE_SLOTS.every(f => next[f.key]?.uploaded));
        return next;
      });
    } catch (err: any) {
      setSlots(prev => ({
        ...prev,
        [key]: { ...prev[key], uploading:false, uploaded:false, error: err?.message || "Upload failed" }
      }));
    }
  }, [onAllReady]);

  const removeFile = async (key: string) => {
    try {
      await api.deleteUpload(key);
      setSlots(prev => {
        const next = { ...prev, [key]: { ...prev[key], uploaded:false, size_kb:0, error:null } };
        onAllReady(false);
        return next;
      });
    } catch {}
  };

  // ── Voice memo upload ──────────────────────────────────────────────────────
  const uploadVoiceMemos = useCallback(async (files: FileList | File[]) => {
    const arr = Array.from(files);
    const valid = arr.filter(f => AUDIO_FORMATS.some(ext => f.name.toLowerCase().endsWith(ext)));
    const invalid = arr.filter(f => !AUDIO_FORMATS.some(ext => f.name.toLowerCase().endsWith(ext)));

    if (invalid.length > 0) {
      setVoiceError(`Unsupported format: ${invalid.map(f => f.name).join(", ")}. Use: ${AUDIO_FORMATS.join(" ")}`);
    } else {
      setVoiceError(null);
    }

    if (valid.length === 0) return;
    setVoiceUploading(true);

    try {
      const result = await api.uploadVoiceMemos(valid);
      if (result.files) {
        setVoiceMemos(prev => [
          ...prev,
          ...result.files.filter((f: any) => f.status === "uploaded")
        ]);
      }
    } catch (err: any) {
      setVoiceError(err?.message || "Upload failed");
    } finally {
      setVoiceUploading(false);
    }
  }, []);

  const removeVoiceMemo = async (filename: string) => {
    try {
      await api.deleteVoiceMemo(filename);
      setVoiceMemos(prev => prev.filter(m => m.filename !== filename));
    } catch {}
  };

  const uploadedCount = FILE_SLOTS.filter(f => slots[f.key]?.uploaded).length;

  return (
    <div className="flex flex-col items-center justify-center min-h-full py-10 px-6 animate-fade-up">

      {/* Title */}
      <div className="text-center mb-8">
        <div className="display font-black text-5xl text-[var(--amber)] tracking-tight mb-1">
          WAREHOUSE<span className="text-[var(--text)]">IQ</span>
          <span className="text-[var(--amber)] animate-blink">_</span>
        </div>
        <p className="mono text-[10px] text-[var(--muted)] tracking-widest uppercase">
          LangGraph · 5-Agent Agentic System
        </p>
        <p className="mono text-xs text-[var(--muted)] mt-3">
          Upload your warehouse data files to begin · Voice memos are optional
        </p>
      </div>

      {/* Required: 4 structured files */}
      <div className="w-full max-w-2xl mb-4">
        <p className="section-label mb-3">Required — 4 Structured Data Files</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {FILE_SLOTS.map(slot => {
            const s = slots[slot.key];
            return (
              <div
                key={slot.key}
                onDragOver={e => { e.preventDefault(); setSlots(prev => ({...prev,[slot.key]:{...prev[slot.key],dragOver:true}})); }}
                onDragLeave={() => setSlots(prev => ({...prev,[slot.key]:{...prev[slot.key],dragOver:false}}))}
                onDrop={e => { e.preventDefault(); setSlots(prev=>({...prev,[slot.key]:{...prev[slot.key],dragOver:false}})); const f=e.dataTransfer.files[0]; if(f) uploadFile(slot.key,f); }}
                onClick={() => !s.uploaded && !s.uploading && fileInputRefs.current[slot.key]?.click()}
                className={`relative border transition-all select-none p-4
                  ${s.uploaded
                    ? "border-[var(--ok)]/40 bg-[var(--ok)]/5 cursor-default"
                    : s.dragOver
                    ? "border-[var(--amber)] bg-[var(--amber)]/10 scale-[1.01]"
                    : s.error
                    ? "border-[var(--danger)]/40 bg-[var(--danger)]/5 cursor-pointer"
                    : "border-[var(--border)] bg-[var(--ink2)] hover:border-[var(--amber)]/40 cursor-pointer"
                  }`}
              >
                <input
                  type="file"
                  accept={slot.format === "JSON" ? ".json" : ".csv"}
                  className="hidden"
                  ref={el => { fileInputRefs.current[slot.key] = el; }}
                  onChange={e => { const f=e.target.files?.[0]; if(f) uploadFile(slot.key,f); }}
                />
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{slot.icon}</span>
                    <div>
                      <p className={`display font-bold text-sm ${s.uploaded ? "text-[var(--ok)]" : "text-[var(--text)]"}`}>
                        {slot.label}
                      </p>
                      <p className="mono text-[9px] text-[var(--muted)]">{slot.filename}</p>
                    </div>
                  </div>
                  <span className={`chip ${slot.format === "JSON" ? "chip-amber" : "chip-muted"}`}>{slot.format}</span>
                </div>

                {s.uploading ? (
                  <p className="mono text-[10px] text-[var(--amber)] animate-pulse mt-2">⟳ Uploading...</p>
                ) : s.uploaded ? (
                  <div className="flex items-center justify-between mt-2">
                    <span className="mono text-[10px] text-[var(--ok)]">✓ {s.size_kb} KB</span>
                    <button onClick={e=>{e.stopPropagation();removeFile(slot.key);}}
                      className="mono text-[9px] text-[var(--muted)] hover:text-[var(--danger)] transition-colors">
                      ✕ remove
                    </button>
                  </div>
                ) : s.error ? (
                  <div className="mt-2">
                    <p className="mono text-[10px] text-[var(--danger)]">✗ {s.error}</p>
                    <p className="mono text-[9px] text-[var(--muted)]">Click to retry</p>
                  </div>
                ) : (
                  <div className="mt-2 border border-dashed border-[var(--border)] py-2 text-center">
                    <p className="mono text-[10px] text-[var(--muted)]">
                      {s.dragOver ? "Drop it!" : "Drag & drop or click"}
                    </p>
                    <p className="mono text-[8px] text-[var(--muted)]/50 mt-1">{slot.hint}</p>
                  </div>
                )}
                {s.dragOver && <div className="absolute inset-0 pointer-events-none border-2 border-[var(--amber)] animate-pulse-amb" />}
              </div>
            );
          })}
        </div>
      </div>

      {/* Optional: Voice memos */}
      <div className="w-full max-w-2xl mb-6">
        <div className="flex items-center gap-2 mb-3">
          <p className="section-label">Optional — Voice Memos</p>
          <span className="chip chip-muted">AUDIO</span>
          <span className="mono text-[9px] text-[var(--muted)]">Transcribed by AWS Transcribe + Nova Lite</span>
        </div>

        <div
          onDragOver={e=>{e.preventDefault();setVoiceDragOver(true);}}
          onDragLeave={()=>setVoiceDragOver(false)}
          onDrop={e=>{e.preventDefault();setVoiceDragOver(false);if(e.dataTransfer.files.length>0) uploadVoiceMemos(e.dataTransfer.files);}}
          onClick={()=>voiceInputRef.current?.click()}
          className={`relative border transition-all cursor-pointer p-4
            ${voiceDragOver
              ? "border-[var(--amber)] bg-[var(--amber)]/10"
              : "border-[var(--border)] bg-[var(--ink2)] hover:border-[var(--amber)]/40"
            }`}
        >
          <input
            type="file"
            multiple
            accept={AUDIO_FORMATS.join(",")}
            className="hidden"
            ref={voiceInputRef}
            onChange={e=>{if(e.target.files) uploadVoiceMemos(e.target.files);}}
          />

          <div className="flex items-center gap-3 mb-3">
            <span className="text-2xl">🎙</span>
            <div>
              <p className="display font-bold text-sm text-[var(--text)]">Warehouse Voice Memos</p>
              <p className="mono text-[9px] text-[var(--muted)]">
                {AUDIO_FORMATS.join(" · ")}  ·  Multiple files allowed
              </p>
            </div>
            {voiceUploading && (
              <span className="mono text-[10px] text-[var(--amber)] animate-pulse ml-auto">⟳ Uploading...</span>
            )}
          </div>

          {/* Uploaded memos list */}
          {voiceMemos.length > 0 ? (
            <div className="space-y-1 mb-3">
              {voiceMemos.map(memo => (
                <div key={memo.filename} className="flex items-center justify-between py-1 border-b border-[var(--border)]">
                  <div className="flex items-center gap-2">
                    <span className="text-[var(--ok)] text-xs">✓</span>
                    <span className="mono text-[9px] text-[var(--text)]">{memo.filename}</span>
                    <span className="mono text-[9px] text-[var(--muted)]">{memo.size_kb} KB</span>
                  </div>
                  <button
                    onClick={e=>{e.stopPropagation();removeVoiceMemo(memo.filename);}}
                    className="mono text-[9px] text-[var(--muted)] hover:text-[var(--danger)] transition-colors"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          ) : null}

          <div className={`border border-dashed py-2 text-center transition-colors
            ${voiceDragOver ? "border-[var(--amber)]" : "border-[var(--border)]"}`}>
            <p className="mono text-[10px] text-[var(--muted)]">
              {voiceDragOver
                ? "Drop audio files here!"
                : voiceMemos.length > 0
                ? `${voiceMemos.length} file${voiceMemos.length>1?"s":""} uploaded · Drop more to add`
                : "Drag & drop audio files or click to browse"
              }
            </p>
          </div>

          {voiceError && (
            <p className="mono text-[10px] text-[var(--danger)] mt-2">✗ {voiceError}</p>
          )}

          <p className="mono text-[8px] text-[var(--muted)]/50 mt-2">
            Each file is transcribed during pipeline ingestion · Results appear in the Records tab as source_type=voice
          </p>
        </div>
      </div>

      {/* Progress */}
      <div className="w-full max-w-2xl mb-6">
        <div className="flex justify-between items-center mb-1.5">
          <span className="section-label">Required Files</span>
          <span className="mono text-[10px] text-[var(--muted)]">
            {uploadedCount} / {FILE_SLOTS.length} ready
            {voiceMemos.length > 0 && ` · ${voiceMemos.length} voice memo${voiceMemos.length>1?"s":""}`}
          </span>
        </div>
        <div className="h-1 bg-[var(--border)] w-full">
          <div className="h-1 bg-[var(--amber)] transition-all duration-500"
               style={{width:`${(uploadedCount/FILE_SLOTS.length)*100}%`}} />
        </div>
      </div>

      {/* Run button */}
      <div className="w-full max-w-2xl">
        {allUploaded ? (
          <div className="animate-fade-up">
            <div className="card-amber p-4 mb-3 flex items-center gap-3">
              <span className="text-[var(--amber)] text-xl">⬡</span>
              <div>
                <p className="display font-bold text-sm text-[var(--amber)]">
                  All files ready — LangGraph pipeline armed
                </p>
                <p className="mono text-[9px] text-[var(--muted)] mt-0.5">
                  {voiceMemos.length > 0
                    ? `Ingesting ${voiceMemos.length} voice memo${voiceMemos.length>1?"s":""} + 4,000 structured records`
                    : "Ingesting 4,000 structured records · Upload voice memos above to add more"}
                </p>
              </div>
            </div>
            <button onClick={onRun} disabled={loading} className="btn-primary w-full text-base py-3">
              {loading ? "⟳  STARTING LANGGRAPH..." : "▶  RUN AGENTIC PIPELINE"}
            </button>
          </div>
        ) : (
          <div className="card p-4 text-center">
            <p className="mono text-[10px] text-[var(--muted)]">
              Upload the 4 required files above to enable the pipeline
            </p>
          </div>
        )}
      </div>
    </div>
  );
}