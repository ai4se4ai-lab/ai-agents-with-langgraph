import { Fragment, useEffect, useRef, useState } from "react";
import { NODES, nodeForStep } from "./loopMap";
import { actLabel, type McpServer } from "./mcp";

const API = import.meta.env.VITE_GATEWAY || "http://127.0.0.1:8765";

type LoopEvent = {
  run_id?: string;
  step?: string;
  text?: string;
  observation?: string;
  input?: string;
  tool?: string;
  mcp_server?: string;
  mcp_tool?: string;
};

type TranscriptEntry = { step: string; body: string };

type Skill = { name: string; description: string };

function toWs(httpUrl: string): string {
  return httpUrl.replace(/^http/, "ws");
}

function entryFor(event: LoopEvent): TranscriptEntry {
  const body =
    event.step === "act"
      ? [actLabel(event), event.input || event.text || ""].filter(Boolean).join(" ")
      : event.text || event.observation || event.input || event.tool || "";
  return {
    step: event.step ?? "?",
    body,
  };
}

function groupDiscussions(entries: TranscriptEntry[]): TranscriptEntry[][] {
  const groups: TranscriptEntry[][] = [];
  for (const entry of entries) {
    if (entry.step === "task" || groups.length === 0) {
      groups.push([entry]);
    } else {
      groups[groups.length - 1].push(entry);
    }
  }
  return groups;
}

function splitDiscussion(entries: TranscriptEntry[]): {
  task: TranscriptEntry[];
  thinking: TranscriptEntry[];
  final: TranscriptEntry[];
} {
  const task: TranscriptEntry[] = [];
  const thinking: TranscriptEntry[] = [];
  const final: TranscriptEntry[] = [];
  for (const entry of entries) {
    if (entry.step === "task") task.push(entry);
    else if (entry.step === "success") final.push(entry);
    else thinking.push(entry);
  }
  return { task, thinking, final };
}

function VisibleBlock({ entry }: { entry: TranscriptEntry }) {
  return (
    <div className="transcript-block">
      <div className="step">[{entry.step}]</div>
      {entry.body && <div className="body">{entry.body}</div>}
    </div>
  );
}

function ThinkingToggle({ entries }: { entries: TranscriptEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <details className="transcript-step">
      <summary>
        <span className="step">thinking</span>
      </summary>
      <div className="thinking-body">
        {entries.map((entry, i) => (
          <div key={i} className="thinking-step">
            <div className="step">[{entry.step}]</div>
            {entry.body && <div className="body">{entry.body}</div>}
          </div>
        ))}
      </div>
    </details>
  );
}

function Discussion({ entries }: { entries: TranscriptEntry[] }) {
  const { task, thinking, final } = splitDiscussion(entries);
  return (
    <div className="discussion">
      {task.map((entry, i) => (
        <VisibleBlock key={`task-${i}`} entry={entry} />
      ))}
      <ThinkingToggle entries={thinking} />
      {final.map((entry, i) => (
        <VisibleBlock key={`final-${i}`} entry={entry} />
      ))}
    </div>
  );
}

function isFailedObserve(event: LoopEvent): boolean {
  if (event.step === "error") return true;
  const blob = `${event.observation ?? ""} ${event.text ?? ""}`;
  return event.step === "observe" && /error|failed/i.test(blob);
}

export default function App() {
  const [task, setTask] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [active, setActive] = useState("task");
  const [reuseLit, setReuseLit] = useState(false);
  const [observeFail, setObserveFail] = useState(false);
  const [entries, setEntries] = useState<TranscriptEntry[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [activeModel, setActiveModel] = useState("");
  const [memory, setMemory] = useState("");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [used, setUsed] = useState<string[]>([]);
  const [health, setHealth] = useState("connecting…");
  const logRef = useRef<HTMLDivElement>(null);

  function applyEvent(event: LoopEvent) {
    const step = event.step ?? "";
    setActive(nodeForStep(step));
    if (step === "memory_update") setReuseLit(true);
    if (isFailedObserve(event)) setObserveFail(true);
    if (event.mcp_server) {
      setUsed((prev) => (prev.includes(event.mcp_server!) ? prev : [...prev, event.mcp_server!]));
    }
    setEntries((prev) => [...prev, entryFor(event)]);
    if (step === "memory_update") {
      void refreshSide();
      setRunId(null);
      setActive("task");
    }
  }

  async function refreshSide() {
    try {
      const [mem, sk, mcp] = await Promise.all([
        fetch(`${API}/memory`).then((r) => r.json()),
        fetch(`${API}/skills`).then((r) => r.json()),
        fetch(`${API}/mcp`).then((r) => r.json()),
      ]);
      setMemory(mem.snapshot ?? "");
      setSkills(sk.skills ?? []);
      setMcpServers(mcp.servers ?? []);
    } catch {
      /* gateway may be down */
    }
  }

  useEffect(() => {
    let ws: WebSocket | undefined;
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    async function boot() {
      try {
        const h = await fetch(`${API}/health`).then((r) => r.json());
        setHealth(
          `${h.ok ? "ok" : "down"} · ${h.active_model || "no model"}${h.error ? ` · ${h.error}` : ""}`,
        );
      } catch {
        setHealth(`unreachable · ${API}`);
      }
      try {
        const m = await fetch(`${API}/models`).then((r) => r.json());
        setModels(m.models ?? []);
        setActiveModel(m.active ?? "");
      } catch {
        setModels([]);
      }
      await refreshSide();
    }
    void boot();
    function connect() {
      if (stopped) return;
      ws = new WebSocket(toWs(`${API}/ws/events`));
      ws.onmessage = (ev) => {
        try {
          applyEvent(JSON.parse(ev.data) as LoopEvent);
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        if (!stopped) retry = setTimeout(connect, 1000);
      };
    }
    connect();
    return () => {
      stopped = true;
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, []);

  useEffect(() => {
    const last = entries[entries.length - 1];
    if (last?.step === "task") {
      logRef.current?.scrollTo(0, 0);
    }
  }, [entries]);

  async function send() {
    const text = task.trim();
    if (!text) return;
    setActive("task");
    setReuseLit(false);
    setObserveFail(false);
    setUsed([]);
    setEntries((prev) => [...prev, { step: "task", body: text }]);
    const res = await fetch(`${API}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: text }),
    });
    if (!res.ok) {
      const err = await res.text();
      setEntries((prev) => [...prev, { step: "error", body: err }]);
      setObserveFail(true);
      setActive(nodeForStep("error"));
      return;
    }
    const data = (await res.json()) as { run_id: string };
    setRunId(data.run_id);
    setTask("");
  }

  async function stop() {
    if (!runId) return;
    await fetch(`${API}/runs/${runId}/stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note: "" }),
    });
  }

  async function reloadMcp() {
    await fetch(`${API}/mcp/reload`, { method: "POST" });
    await refreshSide();
  }

  async function onModel(name: string) {
    setActiveModel(name);
    await fetch(`${API}/models/active`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: name }),
    });
  }

  return (
    <div className="app">
      <header className="mast">
        <h1 className="wordmark">
          LOOP
          <span>exp1 · reason ⇄ act ⇄ observe</span>
        </h1>
        <div className="composer">
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="type a task…"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <button type="button" onClick={() => void send()}>
            Send
          </button>
          <button type="button" className="stop" onClick={() => void stop()} disabled={!runId}>
            Stop
          </button>
        </div>
        <div className="health">
          gateway <strong>{API.replace(/^https?:\/\//, "")}</strong>
          <div>{health}</div>
        </div>
      </header>

      <main className="board">
        <section className="panel">
          <h2>graph</h2>
          <div className="rail">
            {NODES.map((node) => {
              const lit = node === active || (node === "reuse" && reuseLit);
              const fail = node === "observe" && observeFail;
              return (
                <div key={node} className={`node${lit ? " lit" : ""}${fail ? " fail" : ""}`}>
                  <span className="dot" />
                  <span className="label">{node}</span>
                </div>
              );
            })}
          </div>
        </section>

        <section className="panel">
          <h2>transcript</h2>
          <div className="transcript" ref={logRef}>
            {groupDiscussions(entries)
              .toReversed()
              .map((group, gi, all) => {
                const originalIndex = all.length - 1 - gi;
                return (
                  <Fragment key={originalIndex}>
                    {gi > 0 && <div className="transcript-sep">discussion</div>}
                    <Discussion entries={group} />
                  </Fragment>
                );
              })}
          </div>
        </section>

        <aside className="panel">
          <h2>side</h2>
          <div className="side">
            <div>
              <label htmlFor="model">model</label>
              <select id="model" value={activeModel} onChange={(e) => void onModel(e.target.value)}>
                {models.length === 0 && <option value="">(none)</option>}
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label>memory</label>
              <pre>{memory || "(empty)"}</pre>
            </div>
            <div>
              <label>skills</label>
              <ul className="skills">
                {skills.map((s) => (
                  <li key={s.name}>
                    <b>{s.name}</b>
                    <div>{s.description}</div>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <label>MCPs this run</label>
              <button type="button" onClick={() => void reloadMcp()}>Reload</button>
              <ul className="skills mcp-list">
                {mcpServers.length === 0 && <li>(none configured)</li>}
                {mcpServers.map((s) => (
                  <li key={s.name} className={used.includes(s.name) ? "used" : ""}>
                    <b>{s.name}</b>
                    <div>
                      {s.connected ? "connected" : s.enabled ? "error" : "disabled"}
                      {used.includes(s.name) ? " · used" : ""}
                      {s.last_error ? ` · ${s.last_error}` : ""}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </aside>
      </main>
    </div>
  );
}
