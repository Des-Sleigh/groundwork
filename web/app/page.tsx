"use client";

import { useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Step = { kind: string; label: string; detail?: unknown; role: string; at: number };
type Flag = { url: string; matches: string[] };
type Grounding = { summary: string; verified: number; total: number };
type WorkerResult = { task: string; grounding: Grounding; injection_flags: Flag[]; sources: { url: string; title: string }[] };
type Result = {
  answer: string;
  n_tasks: number; n_accepted: number; n_revised: number; rejected_tasks: string[];
  cost: { total_usd: number; by_role: Record<string, { cost_usd: number; calls: number }> };
  worker_results: WorkerResult[];
};

const EXAMPLE = "How are mid-market logistics firms using AI for demand forecasting, and what ROI evidence exists?";

export default function Home() {
  const [question, setQuestion] = useState(EXAMPLE);
  const [running, setRunning] = useState(false);
  const [mode, setMode] = useState<string>("");
  const [steps, setSteps] = useState<Step[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string>("");
  const traceRef = useRef<HTMLDivElement>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (running || !question.trim()) return;
    setRunning(true); setSteps([]); setResult(null); setError(""); setMode("");

    try {
      const resp = await fetch(`${API}/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  const flags = (result?.worker_results || []).flatMap((w) => w.injection_flags);
  const sources = dedupe((result?.worker_results || []).flatMap((w) => w.sources), (s) => s.url);
  const verified = (result?.worker_results || []).reduce((a, w) => a + w.grounding.verified, 0);
  const total = (result?.worker_results || []).reduce((a, w) => a + w.grounding.total, 0);
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
