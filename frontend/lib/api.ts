const B = "/api";

async function _check(res: Response) {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  // ── Upload ──────────────────────────────────────────────────────────────────
  getUploadStatus: () => fetch(`${B}/upload/status`).then(r => r.json()),

  uploadFile: async (fileKey: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file, file.name);
    return _check(await fetch(`${B}/upload/${fileKey}`, { method: "POST", body: fd }));
  },

  deleteUpload: (fileKey: string) =>
    fetch(`${B}/upload/${fileKey}`, { method: "DELETE" }).then(r => r.json()),

  uploadVoiceMemos: async (files: File[]) => {
    const fd = new FormData();
    files.forEach(f => fd.append("files", f, f.name));
    return _check(await fetch(`${B}/upload/voicememos`, { method: "POST", body: fd }));
  },

  deleteVoiceMemo: (filename: string) =>
    fetch(`${B}/upload/voicememos/${encodeURIComponent(filename)}`, { method: "DELETE" }).then(r => r.json()),


  // ── Pipeline ─────────────────────────────────────────────────────────────────
  runPipeline:  () => fetch(`${B}/pipeline/run`, { method:"POST" }),
  getStatus:    () => fetch(`${B}/pipeline/status`).then(r=>r.json()),

  // ── Results ──────────────────────────────────────────────────────────────────
  getResults:   () => fetch(`${B}/results`).then(r=>r.json()),
  getPatterns:  () => fetch(`${B}/results/patterns`).then(r=>r.json()),
  getActions:   () => fetch(`${B}/results/actions`).then(r=>r.json()),
  getAlerts:    () => fetch(`${B}/results/alerts`).then(r=>r.json()),
  getStats:     () => fetch(`${B}/results/stats`).then(r=>r.json()),
  getRecords:   () => fetch(`${B}/results/records`).then(r=>r.json()),

  // ── Query / Voice ─────────────────────────────────────────────────────────
  query: (question: string) =>
    fetch(`${B}/query`,{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({question})}).then(r=>r.json()),

  voiceAudio: (blob: Blob) => {
    const fd = new FormData(); fd.append("file",blob,"audio.webm");
    return fetch(`${B}/voice/audio`,{method:"POST",body:fd}).then(r=>r.json());
  },
  resetVoice: () =>
  fetch(`${B}/voice/reset`, { method: "POST" }).then(r => r.json()),
};

export type PipelineStatus = {
  running:boolean; step:string|null; progress:number;
  message:string; complete:boolean; error:string|null;
};
export type Pattern = {
  pattern_id:string; title:string; severity:"critical"|"high"|"medium"|"low";
  data_sources:string[]; warehouses:string[]; shifts_affected:string;
  occurrence_count:number; description:string; root_cause:string;
  evidence:string[]; actions:{action:string;owner:string;urgency:string}[];
  impact:string;
};
export type ActionItem = {
  action_id:string; priority:"immediate"|"this_week"|"this_month";
  title:string; description:string; owner:string; pattern_ref:string;
  warehouses:string[]; deadline_days:number; kpi:string; estimated_impact:string;
};
export type Alert = {
  alert_id:string; severity:string; emoji:string; title:string;
  warehouses:string[]; shifts:string; sources:string[];
  occurrences:number; summary:string; top_action:string;
};
export type Record_ = {
  id:string; source_type:"debrief"|"safety"|"qc"|"returns"|"voice";
  date:string; warehouse_id:string|null; zone:string|null; shift:string|null;
  text:string; severity:string; tags:string[];
  analysis?:{sentiment:string;sentiment_score:number;themes:string[];
             anomaly:boolean;anomaly_reason:string|null;
             issues:{type:string;description:string;severity:string}[];
             requires_followup:boolean;summary:string};
};