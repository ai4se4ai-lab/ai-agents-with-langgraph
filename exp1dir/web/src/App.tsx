import { useEffect, useRef, useState } from "react";
import { NODES, nodeForStep } from "./loopMap";

const API = import.meta.env.VITE_GATEWAY || "http://127.0.0.1:8765";

type LoopEvent = {
  run_id?: string;
  step?: string;
  text?: string;
  observation?: string;
  input?: string;
  tool?: string;
};

type Skill = { name: string; description: string };

function toWs(httpUrl: string): string {
  return httpUrl.replace(/^http/, "ws");
}

function lineFor(event: LoopEvent): string {
  const body = event.text || event.observation || event.input || event.tool || "";
  return `[${event.step ?? "?"}] ${body}`;
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
  const [lines, setLines] = useState<string[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [activeModel, setActiveModel] = useState("");
  const [memory, setMemory] = useState("");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [health, setHealth] = useState("connecting…");
  const logRef = useRef<HTMLPreElement>(null);

  function applyEvent(event: LoopEvent) {
    const step = event.step ?? "";
    setActive(nodeForStep(step));
    if (step === "memory_update") setReuseLit(true);
    if (isFailedObserve(event)) setObserveFail(true);
    setLines((prev) => [...prev, lineFor(event)]);
    if (step === "memory_update") {
      void refreshSide();
    }
  }

  async function refreshSide() {
    try {
      const [mem, sk] = await Promise.all([
        fetch(`${API}/memory`).then((r) => r.json()),
        fetch(`${API}/skills`).then((r) => r.json()),
      ]);
      setMemory(mem.snapshot ?? "");
      setSkills(sk.skills ?? []);
    } catch {
      /* gateway may be down */
    }
  }

  useEffect(() => {
    let ws: WebSocket | undefined;
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
    ws = new WebSocket(toWs(`${API}/ws/events`));
    ws.onmessage = (ev) => {
      try {
        applyEvent(JSON.parse(ev.data) as LoopEvent);
      } catch {
        /* ignore malformed frames */
      }
    };
    return () => ws?.close();
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo(0, logRef.current.scrollHeight);
  }, [lines]);

  async function send() {
    const text = task.trim();
    if (!text) return;
    setActive("task");
    setReuseLit(false);
    setObserveFail(false);
    setLines((prev) => [...prev, `[task] ${text}`]);
    const res = await fetch(`${API}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: text }),
    });
    if (!res.ok) {
      const err = await res.text();
      setLines((prev) => [...prev, `[error] ${err}`]);
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
    await fetch(`${API}/runs/${runId}/interrupt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note: "" }),
    });
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
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
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
          <pre className="transcript" ref={logRef}>
            {lines.map((line, i) => {
              const m = line.match(/^\[([^\]]+)\] (.*)$/s);
              if (!m) return <div key={i}>{line}</div>;
              return (
                <div key={i}>
                  <span className="step">[{m[1]}]</span> {m[2]}
                </div>
              );
            })}
          </pre>
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
          </div>
        </aside>
      </main>
    </div>
  );
}
