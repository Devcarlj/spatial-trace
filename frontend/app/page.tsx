"use client";
import Image from "next/image";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
type Hit = {
    frame_id: string;
    frame_url?: string;
    ts?: number;
    bbox?: number[];
};
type Result = {
    state: string;
    answer: string;
    frame_url?: string;
    bbox?: number[];
    trail: Hit[];
};
async function post<T>(path: string, payload: object): Promise<T> {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await r.json();
    if (!r.ok)
        throw new Error(typeof data.detail === "string" ? data.detail : "Check your inputs and try again.");
    return data;
}
export default function Home() {
    const [video, setVideo] = useState(""), [clip, setClip] = useState(""), [query, setQuery] = useState(""), [mode, setMode] = useState("connecting");
    const [busy, setBusy] = useState(""), [notice, setNotice] = useState(""), [error, setError] = useState("");
    const [result, setResult] = useState<Result | null>(null), [selected, setSelected] = useState<Hit | null>(null), [size, setSize] = useState([1, 1]);
    useEffect(() => { fetch("/api/health").then(r => { if (!r.ok)
        throw Error(); return r.json(); }).then(r => setMode(r.mode)).catch(() => setMode("unavailable")); }, []);
    async function index(e: FormEvent) {
        e.preventDefault();
        setBusy("index");
        setError("");
        setNotice("");
        setResult(null);
        setSelected(null);
        try {
            const r = await post<{
                indexed_frame_count: number;
            }>("/api/index", { video_path: video.trim(), clip_id: clip.trim() });
            setNotice(`Indexed ${r.indexed_frame_count} frame(s). Your clip is ready to search.`);
        }
        catch (e) {
            setError(e instanceof Error ? e.message : "Indexing failed.");
        }
        finally {
            setBusy("");
        }
    }
    async function search(e: FormEvent) {
        e.preventDefault();
        setBusy("query");
        setError("");
        setResult(null);
        setSelected(null);
        try {
            setResult(await post<Result>("/api/query", { query: query.trim() }));
        }
        catch (e) {
            setError(e instanceof Error ? e.message : "Search failed.");
        }
        finally {
            setBusy("");
        }
    }
    const image = selected?.frame_url ?? result?.frame_url, box = selected?.bbox ?? result?.bbox;
    return <main className="workspace">
 <header><Link className="brand" href="/">SpatialTrace <small>MEMORY, IN VIEW</small></Link><span>{mode === "live" ? "● Live models" : mode === "mock" ? "● Demo models" : mode === "unavailable" ? "Backend unavailable" : "Connecting…"}</span></header>
 <section className="intro"><p className="eyebrow">YOUR VISUAL MEMORY</p><h1>Find what you last saw.</h1><p>Index a recorded moment. Ask about an object. Follow the evidence back to its location.</p></section>
 <div className="columns"><aside>
 <form onSubmit={index}><p className="eyebrow">01 / ADD A MEMORY</p><h2>Index a video</h2><label htmlFor="video">Video path on this computer</label><input id="video" value={video} onChange={e => setVideo(e.target.value)} placeholder="C:\\Videos\\desk.mp4" required disabled={!!busy}/><p className="hint">Use a full path accessible to the local backend.</p><label htmlFor="clip">Clip name</label><input id="clip" value={clip} onChange={e => setClip(e.target.value)} placeholder="desk-morning-01" pattern="[A-Za-z0-9_-]+" required disabled={!!busy}/><button disabled={!!busy}>{busy === "index" ? "Indexing video…" : "Index video →"}</button></form>
 <form onSubmit={search}><p className="eyebrow">02 / FIND AN OBJECT</p><h2>Ask your memory</h2><label htmlFor="query">What are you looking for?</label><input id="query" value={query} onChange={e => setQuery(e.target.value)} placeholder="Where are my glasses?" required disabled={!!busy}/><button disabled={!!busy}>{busy === "query" ? "Looking through frames…" : "Search memory →"}</button></form>
 <div aria-live="polite">{notice && <p className="notice">{notice}</p>}{error && <p role="alert" className="error">{error}</p>}</div></aside>
 <section className="evidence" aria-live="polite"><div className="evidence-heading"><h2>Evidence</h2><span>{result ? result.state.replaceAll("_", " ") : "Awaiting a query"}</span></div>
 {busy ? <div className="empty"><b>+</b><h3>{busy === "index" ? "Building your visual memory" : "Checking the saved frames"}</h3><p>This can take a moment while the models inspect the footage.</p></div> : result ? <>{image && <div className="frame"><Image unoptimized width={768} height={576} src={image} alt="Matching historical video frame" onLoad={e => setSize([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight])}/>{box && <svg className="overlay" viewBox={`0 0 ${size[0]} ${size[1]}`} aria-label="Detected object bounding box"><rect x={box[0]} y={box[1]} width={box[2] - box[0]} height={box[3] - box[1]} fill="none" stroke={result.state === "UNSURE" ? "#c29031" : "#a8ec87"} strokeWidth="3" vectorEffect="non-scaling-stroke" strokeDasharray={result.state === "UNSURE" ? "8 5" : undefined}/></svg>}</div>}<div className="answer"><p className="eyebrow">{result.state === "UNSURE" ? "POSSIBLE MATCH" : "LAST VERIFIED SIGHTING"}</p><p>{result.answer}</p></div>{result.trail.length > 0 && <div className="timeline"><h3>Sighting trail</h3>{result.trail.map(hit => <button className={selected?.frame_id === hit.frame_id ? "sighting active" : "sighting"} key={hit.frame_id} onClick={() => setSelected(hit)}><span>{(hit.ts ?? 0).toFixed(1)}s</span><span>View frame ↗</span></button>)}</div>}</> : <div className="empty"><b>+</b><h3>A frame worth remembering</h3><p>Your matching frame, object location, and sighting trail will appear here.</p></div>}</section></div>
 <footer>Recorded observations, not a real-time camera. Search covers all indexed clips.</footer></main>;
}
