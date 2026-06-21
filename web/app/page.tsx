"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Step = { kind: string; label: string; detail?: unknown; role: string; at: number };
type Flag = { url: string; matches: string[] };
type GResult = { claim: string; supported: boolean; evidence: string; best_source_url: string | null; score: number };
type Grounding = { summary: string; verified: number; total: number; results: GResult[] };
type WorkerResult = { task: string; grounding: Grounding; injection_flags: Flag[]; sources: { url: string; title: string }[] };
type Result = {
  answer: string;
  n_tasks: number; n_accepted: number; n_revised: number; rejected_tasks: string[];
  cost: { total_usd: number; by_role: Record<string, { cost_usd: number; calls: number }> };
  worker_results: WorkerResult[];
};
type RunRow = { id: number; question: string; mode: string; grounding_verified: number; grounding_total: number; cost_usd: number };

const EXAMPLES = [
  "How are mid-market logistics firms using AI for demand forecasting, and what ROI evidence exists?",
  "What are the main risks when adopting AI for inventory management?",
  "How do companies measure ROI on generative-AI pilots?",
];

export default function Home() {
  const [question, setQuestion] = useState(EXAMPLES[0]);
  const [running, setRunning] = useState(false);
  const [mode, setMode] = useState<string>("");
  const [steps, setSteps] = useState<Step[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string>("");
  const [history, setHistory] = useState<RunRow[]>([]);
  const [showClaims, setShowClaims] = useState(false);
  const traceRef = useRef<HTMLDivElement>(null);

  const loadHistory = useCallback(async () => {
    try {
      const r = await fetch(`${API}/runs?limit=12`);
      if (r.ok) setHistory((await r.json()).runs || []);
    } catch { /* backend may be down; ignore */ }
  }, []);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  async function openRun(id: number) {
    if (running) return;
    try {
      const r = await fetch(`${API}/runs/${id}`);
      if (!r.ok) return;
      const data = await r.json();
      setResult(data.result as Result);
      setSteps((data.trace || []) as Step[]);
      setMode(data.mode || "");
      setError("");
    } catch { /* ignore */ }
  }

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (running || !question.trim()) return;
    setRunning(true); setSteps([]); setResult(null); setError(""); setMode(""); setShowClaims(false);

    try {
      const resp = await fetch(`${API}/research`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!resp.body) throw new Error("No response stream");
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        for (const chunk of chunks) {
          const line = chunk.trim();
          if (!line.startsWith("data:")) continue;
          const evt = JSON.parse(line.slice(5).trim());
          if (evt.type === "start") setMode(evt.mode);
          else if (evt.type === "step") {
            setSteps((s) => [...s, evt as Step]);
            requestAnimationFrame(() => traceRef.current?.scrollTo(0, 1e9));
          } else if (evt.type === "result") setResult(evt.result as Result);
          else if (evt.type === "error") setError(evt.message);
        }
      }
      loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  const flags = (result?.worker_results || []).flatMap((w) => w.injection_flags);
  const sources = dedupe((result?.worker_results || []).flatMap((w) => w.sources), (s) => s.url);
  const claims = (result?.worker_results || []).flatMap((w) => w.grounding?.results || []);
  const verified = claims.filter((c) => c.supported).length;
  const total = claims.length;
  const roles = result ? Object.entries(result.cost.by_role) : [];
  const maxCost = Math.max(0.0001, ...roles.map(([, v]) => v.cost_usd));

  return (
    <div className="wrap">
      <header className="top">
        <h1>Ground<span className="dot">·</span>work</h1>
        {mode && <span className={`badge ${mode}`}>{mode === "real" ? "live models" : "offline demo"}</span>}
      </header>
      <p className="tagline">
        A grounded, injection-resistant research agent. It plans, gathers sources, synthesizes a cited
        answer, and verifies every claim against those sources — treating fetched content as untrusted
        data. Watch the trajectory live.
      </p>

      <form className="query" onSubmit={run}>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask a research question…" />
        <button disabled={running}>{running ? "Researching…" : "Research"}</button>
      </form>
      <div className="chips">
        {EXAMPLES.map((ex) => (
          <button key={ex} className="chip" type="button" onClick={() => setQuestion(ex)}>{ex.length > 54 ? ex.slice(0, 52) + "…" : ex}</button>
        ))}
      </div>

      {history.length > 0 && (
        <div className="history">
          <h2>Recent runs</h2>
          <div className="runs">
            {history.map((r) => (
              <div key={r.id} className="run" onClick={() => openRun(r.id)}>
                <div className="q">{r.question}</div>
                <div className="meta">
                  <span>{r.grounding_verified}/{r.grounding_total} grounded</span>
                  <span>${r.cost_usd.toFixed(4)}</span>
                  <span>{r.mode}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid">
        <div className="panel">
          <h2>{running && <span className="spinner" />}Agent trajectory</h2>
          <div className="trace" ref={traceRef}>
            {steps.length === 0 && <div className="empty">The plan → tool calls → grounding → critic loop will stream here.</div>}
            {steps.map((s, i) => (
              <div key={i} className={`step ${s.kind === "error" ? "error" : ""}`}>
                <div className={`role ${s.role}`}>{s.role}</div>
                <div>
                  <span className="label">{s.label}</span> <span className="kind">{s.kind}</span>
                  {s.detail != null && <div className="detail">{fmt(s.detail)}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <h2>Result</h2>
          {error && <div className="flag">Error: {error}</div>}
          {!result && !error && <div className="empty">The cited answer, grounding report, injection flags, and cost breakdown appear here.</div>}
          {result && (
            <>
              <Answer text={result.answer} />

              <div style={{ marginTop: 18 }}>
                <div className="kv"><strong style={{ color: "var(--text)" }}>Grounding</strong><span>{verified} / {total} claims verified</span></div>
                <div className="meter"><span style={{ width: `${total ? (verified / total) * 100 : 0}%` }} /></div>
                {total > 0 && (
                  <>
                    <button className="toggle" onClick={() => setShowClaims((v) => !v)}>
                      {showClaims ? "Hide" : "Show"} claim-by-claim verification
                    </button>
                    {showClaims && (
                      <div className="claims">
                        {claims.map((c, i) => (
                          <div key={i} className={`claim ${c.supported ? "ok" : "no"}`}>
                            <span className="mark">{c.supported ? "✓" : "⚠"}</span>
                            <div>
                              {c.claim}
                              {c.evidence && <div className="ev">“{c.evidence}”</div>}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>

              <div style={{ marginTop: 16 }}>
                <div className="kv"><strong style={{ color: "var(--text)" }}>Injection defense</strong><span>{flags.length} flagged</span></div>
                {flags.length === 0 ? (
                  <div className="flag clean">No injection attempts detected in retrieved sources.</div>
                ) : (
                  flags.map((f, i) => (
                    <div key={i} className="flag">caught in {short(f.url)} → {f.matches.join("; ")} (flagged, not obeyed)</div>
                  ))
                )}
              </div>

              <div style={{ marginTop: 16 }}>
                <div className="kv"><strong style={{ color: "var(--text)" }}>Cost by role</strong><span>${result.cost.total_usd.toFixed(4)}</span></div>
                {roles.map(([role, v]) => (
                  <div key={role} className="cost-row">
                    <span className={`role ${role}`}>{role}</span>
                    <span className="bar"><span style={{ width: `${(v.cost_usd / maxCost) * 100}%` }} /></span>
                    <span className="amt">${v.cost_usd.toFixed(4)}</span>
                  </div>
                ))}
                <div className="kv" style={{ marginTop: 8 }}>
                  <span>{result.n_tasks} tasks · {result.n_accepted} accepted · {result.n_revised} revised</span>
                </div>
              </div>

              {sources.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div className="kv"><strong style={{ color: "var(--text)" }}>Sources ({sources.length})</strong></div>
                  {sources.map((s, i) => (
                    <div key={i} className="source"><a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a></div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Answer({ text }: { text: string }) {
  const idx = text.indexOf("\n\n> Grounding:");
  const body = idx >= 0 ? text.slice(0, idx) : text;
  const footer = idx >= 0 ? text.slice(idx).trim() : "";
  return (
    <div className="answer">
      {body}
      {footer && <div className="footer">{footer.replace(/^> ?/gm, "")}</div>}
    </div>
  );
}

function fmt(detail: unknown): string {
  if (typeof detail === "string") return detail;
  try { return JSON.stringify(detail); } catch { return String(detail); }
}
function short(url: string): string {
  try { return new URL(url).hostname + new URL(url).pathname.split("/").pop()!; } catch { return url.slice(-40); }
}
function dedupe<T>(arr: T[], key: (t: T) => string): T[] {
  const seen = new Set<string>();
  return arr.filter((x) => { const k = key(x); if (seen.has(k)) return false; seen.add(k); return true; });
}
