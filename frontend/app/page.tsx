"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { api, PipelineStatus } from "../lib/api";
import Header       from "../components/Header";
import Sidebar      from "../components/Sidebar";
import GraphOverlay from "../components/GraphOverlay";
import UploadScreen from "../components/UploadScreen";
import OverviewTab  from "../components/tabs/OverviewTab";
import PatternsTab  from "../components/tabs/PatternsTab";
import ActionsTab   from "../components/tabs/ActionsTab";
import RecordsTab   from "../components/tabs/RecordsTab";
import VoiceTab     from "../components/tabs/VoiceTab";

export type Tab = "overview"|"patterns"|"actions"|"records"|"voice";
const EMPTY: PipelineStatus = {running:false,step:null,progress:0,message:"",complete:false,error:null};

export default function Page() {
  const [tab,       setTab]       = useState<Tab>("overview");
  const [status,    setStatus]    = useState<PipelineStatus>(EMPTY);
  const [results,   setResults]   = useState<any>(null);   // null = no pipeline run yet
  const [loading,   setLoading]   = useState(false);
  const [showGraph, setShowGraph] = useState(false);
  const [allReady,  setAllReady]  = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval>>();

  const fetchResults = useCallback(async () => {
    try {
      // Use raw fetch so we can check status code before parsing
      const res = await fetch("/api/results");
      if (!res.ok) return;            // 404 = no pipeline run yet, stay on upload screen
      const d = await res.json();
      // Only accept if it has real pipeline output
      if (d?.stats && d?.patterns !== undefined) setResults(d);
    } catch {}
  }, []);

  const checkUploads = useCallback(async () => {
    try {
      const s = await api.getUploadStatus();
      setAllReady(s.all_ready);
    } catch {}
  }, []);

  const poll = useCallback(() => {
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getStatus();
        setStatus(s);
        if (s.complete) {
          clearInterval(pollRef.current);
          setLoading(false);
          await fetchResults();
          setTimeout(() => setShowGraph(false), 1500);
        }
        if (s.error) { clearInterval(pollRef.current); setLoading(false); }
      } catch {}
    }, 900);
  }, [fetchResults]);

  const run = async () => {
    if (loading) return;
    setLoading(true); setShowGraph(true);
    setStatus({...EMPTY, running:true, message:"Starting LangGraph..."});
    try { await api.runPipeline(); poll(); }
    catch { setLoading(false); setShowGraph(false); }
  };

  useEffect(() => {
    fetchResults();
    checkUploads();
    return () => clearInterval(pollRef.current);
  }, [fetchResults, checkUploads]);

  // Show upload screen when no completed pipeline results exist yet
  const showUpload = results === null && !showGraph;

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[var(--ink)]">
      <Header
        status={status} onRun={run} loading={loading}
        alertCount={results?.alerts?.length || 0}
        canRun={allReady}
      />
      <div className="flex flex-1 overflow-hidden">
        {!showUpload && <Sidebar tab={tab} setTab={setTab} results={results} />}
        <main className="flex-1 overflow-y-auto">
          {showGraph ? (
            <GraphOverlay status={status} />
          ) : showUpload ? (
            <UploadScreen
              onAllReady={(ready) => setAllReady(ready)}
              onRun={run}
              loading={loading}
            />
          ) : (
            <div className="p-5 animate-fade-up">
              {tab==="overview"  && <OverviewTab  results={results} />}
              {tab==="patterns"  && <PatternsTab  patterns={results?.patterns||[]} />}
              {tab==="actions"   && <ActionsTab   actions={results?.action_items||[]} />}
              {tab==="records"   && <RecordsTab   records={results?.records||[]} />}
              {tab==="voice"     && <VoiceTab     results={results} />}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}