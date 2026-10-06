"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Model = { id: string; name: string; languages: string; voice: string };
type Job = {
  id: string; title: string; state: "queued" | "running" | "succeeded" | "failed";
  createdAt: string; model: string; voice: string; format: string; host: string;
  log: string; error?: string; downloadable: boolean;
};
type Config = { models: Model[]; hosts: string[]; defaultHost: string; maxUploadMb: number; samplePreview: string };

export default function Home() {
  const [config, setConfig] = useState<Config | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [model, setModel] = useState("pocket");
  const [host, setHost] = useState("");
  const [language, setLanguage] = useState("en");
  const [format, setFormat] = useState("m4b");
  const [workers, setWorkers] = useState("1");
  const [book, setBook] = useState<File | null>(null);
  const [voice, setVoice] = useState<File | null>(null);
  const [voiceInstruction, setVoiceInstruction] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [preview, setPreview] = useState("");
  const [bookTextPreview, setBookTextPreview] = useState("");

  const headers = useMemo<HeadersInit>(() => token ? new Headers({ Authorization: `Bearer ${token}` }) : new Headers(), [token]);
  const refresh = useCallback(async () => {
    try {
      const [configResponse, jobsResponse] = await Promise.all([
        fetch("/api/config", { headers }), fetch("/api/jobs", { headers }),
      ]);
      if (!configResponse.ok || !jobsResponse.ok) throw new Error("Could not connect. Check the access token or server settings.");
      const configData = await configResponse.json() as Config;
      const jobsData = await jobsResponse.json() as { jobs: Job[] };
      setConfig(configData);
      setJobs(jobsData.jobs);
      setHost((current) => current || configData.defaultHost);
      setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Connection failed."); }
  }, [headers]);

  useEffect(() => {
    const stored = sessionStorage.getItem("toni-web-token");
    if (stored) setToken(stored);
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!voice) { setPreview(""); return; }
    const url = URL.createObjectURL(voice);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [voice]);

  const selectedModel = config?.models.find((item) => item.id === model);
  const needsVoice = model === "qwen" || model === "espeech";
  const active = jobs.some((job) => job.state === "running" || job.state === "queued");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!book) { setError("Choose a book file to begin."); return; }
    const formElement = event.currentTarget;
    const form = new FormData();
    form.set("book", book);
    if (voice) form.set("voice", voice);
    if (voiceInstruction && model === "omni" && !voice) form.set("voiceInstruction", voiceInstruction);
    form.set("model", model); form.set("host", host); form.set("language", language);
    form.set("format", format); form.set("workers", workers);
    setBusy(true);
    try {
      const response = await fetch("/api/jobs", { method: "POST", headers, body: form });
      const data = await response.json() as { job?: Job & { preview?: string }; error?: string };
      if (!response.ok) throw new Error(data.error ?? "Could not start render.");
      setBookTextPreview(data.job?.preview ?? "");
      setBook(null); setVoice(null);
      formElement.reset();
      const bookInput = document.querySelector<HTMLInputElement>("#book");
      const voiceInput = document.querySelector<HTMLInputElement>("#voice");
      if (bookInput) bookInput.value = "";
      if (voiceInput) voiceInput.value = "";
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not start render."); }
    finally { setBusy(false); }
  }

  return <main className="shell">
    <header className="topbar"><a className="brand" href="#"><span className="brand-mark">t</span><span>Toni <small>AUDIOBOOK STUDIO</small></span></a><span className="local-badge"><i /> Local library</span></header>
    <section className="intro"><p className="eyebrow">FROM TEXT TO LISTENING</p><h1>Make a book<br /><em>sound like yours.</em></h1><p className="lead">Choose a narrator, add a book, and let the render box do the heavy lifting.</p></section>

    {error && <div className="notice error" role="alert">{error}</div>}
    {!config && <div className="notice">Connecting to your audiobook library…</div>}

    <div className="workspace">
      <section className="panel create-panel">
        <div className="section-heading"><div><span className="step">01</span><h2>Set up your narrator</h2></div><span className="muted">Pick a model and voice</span></div>
        <label className="field-label" htmlFor="model">Text-to-speech model</label>
        <select id="model" value={model} onChange={(event) => setModel(event.target.value)}>
          {(config?.models ?? []).map((item) => <option value={item.id} key={item.id}>{item.name} · {item.languages}</option>)}
        </select>
        <div className="voice-card">
          <div><span className="voice-icon">♫</span><div><strong>{model === "pocket" ? "Alba · casual" : selectedModel?.name ?? "Model voice"}</strong><p>{selectedModel?.voice ?? "Voice options depend on the selected model."}</p></div></div>
          {model === "pocket" && <audio className="sample-audio" controls preload="none" src={config?.samplePreview} aria-label="Listen to the built-in Pocket Alba voice sample" />}
        </div>
        <label className="field-label" htmlFor="voice">Custom voice sample <span className="optional">{needsVoice ? "required for this model" : "optional"}</span></label>
        <label className="upload-row compact" htmlFor="voice"><span className="upload-icon">↑</span><span>{voice ? voice.name : "Upload a short voice recording"}<small>WAV, MP3, M4A, FLAC or OGG</small></span><span className="browse">Browse</span></label>
        <input className="visually-hidden" id="voice" type="file" accept="audio/*,.wav,.flac,.ogg" onChange={(event) => setVoice(event.target.files?.[0] ?? null)} />
        {preview && <audio className="custom-preview" controls src={preview} aria-label="Preview custom voice sample" />}
        {model === "omni" && !voice && <label className="style-field" htmlFor="voice-instruction"><span className="field-label">Describe the narrator <span className="optional">optional · up to 300 characters</span></span><textarea id="voice-instruction" maxLength={300} value={voiceInstruction} onChange={(event) => setVoiceInstruction(event.target.value)} placeholder="For example: warm, measured, and gently expressive." /></label>}
        <p className="helper">A clean 3–10 second sample works best. Only upload a voice you have permission to use.</p>
      </section>

      <section className="panel book-panel">
        <div className="section-heading"><div><span className="step">02</span><h2>Add your book</h2></div><span className="muted">TXT or text-based PDF</span></div>
        <label className="upload-row book-upload" htmlFor="book"><span className="upload-icon">↥</span><span>{book ? book.name : "Choose a book file"}<small>{book ? `${(book.size / 1024 / 1024).toFixed(1)} MB · ready to render` : `UTF-8 text or selectable PDF · up to ${config?.maxUploadMb ?? 100} MB`}</small></span><span className="browse">Browse files</span></label>
        <input className="visually-hidden" id="book" type="file" accept=".txt,.pdf,text/plain,application/pdf" onChange={(event) => { setBook(event.target.files?.[0] ?? null); setBookTextPreview(""); }} />
        {bookTextPreview && <details className="text-preview"><summary>Preview extracted text</summary><pre>{bookTextPreview}</pre></details>}
        <div className="settings-row"><div><label className="field-label" htmlFor="host">Render machine</label><select id="host" value={host} onChange={(event) => setHost(event.target.value)} disabled={!config?.hosts.length}><option value="">Choose configured host</option>{config?.hosts.map((item) => <option key={item} value={item}>{item}</option>)}</select></div><div><label className="field-label" htmlFor="language">Language</label><input id="language" value={language} onChange={(event) => setLanguage(event.target.value)} placeholder="en" /></div></div>
        {!config?.hosts.length && <p className="helper warning">No render machines configured. Add one in the ignored hosts.local.json file.</p>}
        <button type="button" className="advanced-toggle" onClick={() => setAdvanced((value) => !value)}>{advanced ? "− Hide" : "+ Show"} advanced options <span>Output format and worker count</span></button>
        {advanced && <div className="settings-row advanced"><div><label className="field-label" htmlFor="format">Output format</label><select id="format" value={format} onChange={(event) => setFormat(event.target.value)}><option value="m4b">M4B · chapters</option><option value="mp3">MP3</option></select></div><div><label className="field-label" htmlFor="workers">Workers (1–4)</label><input id="workers" type="number" min="1" max="4" value={workers} onChange={(event) => setWorkers(event.target.value)} /></div></div>}
        <button type="submit" form="render-form" className="primary-button" disabled={busy || active || !config?.hosts.length}>{busy ? "Preparing your book…" : active ? "A render is already in progress" : "Start audiobook render"}<span>↗</span></button>
        <p className="fine-print">Long books can take hours. You can leave this page while the render runs.</p>
      </section>
    </div>

    <form id="render-form" onSubmit={submit} className="submit-proxy" aria-hidden="true" />
    <section className="jobs-section"><div className="section-heading jobs-heading"><div><span className="step">03</span><h2>Your audiobooks</h2></div><span className="muted">Updates automatically</span></div>
      {jobs.length === 0 ? <div className="empty-state"><span>◷</span><p>Your renders will appear here.</p><small>Progress, status, and finished audio in one place.</small></div> : <div className="job-list">{jobs.map((job) => <article className="job-card" key={job.id}>
        <div className="job-main"><span className={`state-icon ${job.state}`}>{job.state === "succeeded" ? "✓" : job.state === "failed" ? "!" : "↻"}</span><div className="job-copy"><strong>{job.title}</strong><p>{job.model} · {job.host} · {new Date(job.createdAt).toLocaleString()}</p><span className={`status-text ${job.state}`}>{job.state === "running" ? "Rendering" : job.state === "queued" ? "Queued" : job.state === "succeeded" ? "Ready to download" : job.error ?? "Render failed"}</span></div></div>
        {job.downloadable && <a className="download-button" href={`/api/jobs/${job.id}/download`} onClick={async (event) => { if (token) { event.preventDefault(); const response = await fetch(event.currentTarget.href, { headers }); if (response.ok) { const blob = await response.blob(); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `${job.title.replace(/\.[^.]+$/, "")}.${job.format}`; link.click(); URL.revokeObjectURL(link.href); } } }}>↓ Download {job.format.toUpperCase()}</a>}
        {(job.state === "running" || job.state === "failed") && job.log && <details className="log-view"><summary>{job.state === "running" ? "Recent progress" : "View render log"}</summary><pre>{job.log}</pre></details>}
      </article>)}</div>}
    </section>
    <footer className="footer"><span>TONI AUDIOBOOK STUDIO</span><span>Books and voice samples stay on your server.</span><label className="token-entry">Access token <input type="password" value={token} placeholder="optional" onChange={(event) => { setToken(event.target.value); sessionStorage.setItem("toni-web-token", event.target.value); }} /></label></footer>
  </main>;
}
