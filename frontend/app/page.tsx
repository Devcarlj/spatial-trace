"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import EvidenceFrame, { type MaskOverlay } from "./evidence-frame";

type Hit = {
  frame_id: string;
  frame_url?: string | null;
  ts?: number | null;
  bbox?: number[] | null;
  score?: number | null;
  mask_overlay?: MaskOverlay | null;
  recovered?: boolean;
};
type Result = Omit<Hit, "frame_id"> & {
  frame_id?: string | null;
  state: "FOUND_NOW" | "MOVED" | "UNSURE";
  answer: string;
  movement?: { status: string; reason: string; displacement?: number[]; camera_compensated: boolean } | null;
  trail: Hit[];
};

async function post<T>(path: string, payload: object): Promise<T> {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  let data;
  try { data = await response.json(); }
  catch { throw new Error("The backend could not complete this request. Check that it is running and try again."); }
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Check your inputs and try again.");
  return data;
}

export default function Home() {
  const [video, setVideo] = useState(""), [clip, setClip] = useState(""), [query, setQuery] = useState("");
  const [mode, setMode] = useState("connecting"), [busy, setBusy] = useState("");
  const [notice, setNotice] = useState(""), [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null), [selected, setSelected] = useState<Hit | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/health", { signal: controller.signal }).then(response => {
      if (!response.ok) throw Error();
      return response.json();
    }).then(data => setMode(data.mode)).catch(() => { if (!controller.signal.aborted) setMode("unavailable"); });
    return () => controller.abort();
  }, []);
  function begin(operation: string) {
    setBusy(operation); setError(""); setNotice(""); setResult(null); setSelected(null);
  }
  async function index(event: FormEvent) {
    event.preventDefault(); begin("index");
    try {
      const data = await post<{ indexed_frame_count: number }>("/api/index", { video_path: video.trim(), clip_id: clip.trim() });
      setNotice(`Indexed ${data.indexed_frame_count} observation(s). Your clip is ready to search.`);
    } catch (error) { setError(error instanceof Error ? error.message : "Indexing failed."); }
    finally { setBusy(""); }
  }
  async function search(event: FormEvent) {
    event.preventDefault(); begin("query");
    try { setResult(await post<Result>("/api/query", { query: query.trim() })); }
    catch (error) { setError(error instanceof Error ? error.message : "Search failed."); }
    finally { setBusy(""); }
  }
  const hit = selected ?? result?.trail.find(item => item.frame_id === result.frame_id) ?? result;
  const earlier = selected && selected.frame_id !== result?.frame_id;
  const stateLabel = result?.state === "FOUND_NOW" ? "Found in saved footage" : result?.state === "MOVED" ? "Movement detected" : "Uncertain match";
  return <main className="workspace">
    <header><Link className="brand" href="/">SpatialTrace <small>MEMORY, IN VIEW</small></Link><span>{mode === "live" ? "● Live models" : mode === "mock" ? "● Demo models" : mode === "unavailable" ? "Backend unavailable" : "Connecting…"}</span></header>
    <section className="intro"><p className="eyebrow">YOUR VISUAL MEMORY</p><h1>Find what you last saw.</h1><p>Index a recorded moment. Ask about an object. Follow the evidence back to its location.</p></section>
    <div className="columns"><aside>
      <form onSubmit={index}><p className="eyebrow">01 / ADD A MEMORY</p><h2>Index a video</h2>
        <label htmlFor="video">Video path on this computer</label><input id="video" value={video} onChange={event => setVideo(event.target.value)} placeholder="C:\Videos\desk.mp4" required maxLength={2048} disabled={!!busy} />
        <p className="hint">Use a full path accessible to the local backend.</p>
        <label htmlFor="clip">Clip name</label><input id="clip" value={clip} onChange={event => setClip(event.target.value)} placeholder="desk-morning-01" pattern="[A-Za-z0-9_-]+" maxLength={64} required disabled={!!busy} />
        <button disabled={!!busy}>{busy === "index" ? "Indexing video…" : "Index video →"}</button>
      </form>
      <form onSubmit={search}><p className="eyebrow">02 / FIND AN OBJECT</p><h2>Ask your memory</h2>
        <label htmlFor="query">What are you looking for?</label><input id="query" value={query} onChange={event => setQuery(event.target.value)} placeholder="Where are my glasses?" maxLength={200} required disabled={!!busy} />
        <button disabled={!!busy}>{busy === "query" ? "Looking through frames…" : "Search memory →"}</button>
      </form>
      <div aria-live="polite">{notice && <p className="notice">{notice}</p>}{error && <p role="alert" className="error">{error}</p>}</div>
    </aside>
    <section className="evidence" aria-live="polite" aria-busy={!!busy}>
      <div className="evidence-heading"><h2>Evidence</h2><span>{result ? stateLabel : "Awaiting a query"}</span></div>
      {busy ? <div className="empty"><b className="working">+</b><h3>{busy === "index" ? "Building your visual memory" : "Checking the saved frames"}</h3><p>{busy === "index" ? "Inspecting the recorded footage and saving observations." : "Verifying detections, recovering small objects, and checking movement. This may take a few minutes."}</p></div> : result ? <>
        {hit?.frame_url && <EvidenceFrame key={hit.frame_url} src={hit.frame_url} box={hit.bbox} mask={hit.mask_overlay} uncertain={result.state === "UNSURE"} />}
        {hit?.frame_url && <div className="evidence-meta"><span>{result.state === "UNSURE" ? "Possible observation" : earlier ? "Earlier observation" : "Latest verified observation"}{hit.ts != null ? ` · ${hit.ts.toFixed(1)}s` : ""}</span><span>{hit.score != null ? `Model score ${hit.score.toFixed(2)}` : ""}{hit.recovered ? " · Recovery pass" : ""}</span></div>}
        <div className="answer"><p className="eyebrow">{result.state === "UNSURE" ? "POSSIBLE MATCH" : "LAST VERIFIED SIGHTING"}</p><p>{result.answer}</p>{earlier && <p className="hint">You are viewing an earlier observation. The answer describes the latest verified sighting.</p>}</div>
        {result.movement && <div className="movement"><strong>{result.movement.status === "moved" ? "Movement detected" : result.movement.status === "stationary" ? "Within movement tolerance" : "Movement uncertain"}</strong><p>{result.movement.reason}{result.movement.camera_compensated ? " Camera motion compensated." : ""}</p></div>}
        {result.trail.length > 0 && <div className="timeline"><h3>{result.state === "UNSURE" ? "Possible sighting" : "Associated sighting trail"} · {result.trail.length} observation{result.trail.length === 1 ? "" : "s"}</h3>{result.trail.map(item => <button type="button" aria-pressed={hit?.frame_id === item.frame_id} className={hit?.frame_id === item.frame_id ? "sighting active" : "sighting"} key={item.frame_id} onClick={() => setSelected(item)}><span>{(item.ts ?? 0).toFixed(1)}s{item.frame_id === result.frame_id ? " · Latest" : ""}</span><span>View frame ↗</span></button>)}</div>}
      </> : <div className="empty"><b>+</b><h3>A frame worth remembering</h3><p>Your matching frame, pixel mask, and associated sightings will appear here.</p></div>}
    </section></div>
    <footer>Recorded observations, not a real-time camera. Search covers indexed observations across all clips; footage between observations is unverified.</footer>
  </main>;
}
