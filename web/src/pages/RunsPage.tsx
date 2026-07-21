import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type DatasetSummary } from "../api";
import { fmtNum, fmtPct, fmtTime } from "../format";
import { usePolling } from "../hooks/usePolling";

export function RunsPage() {
  const { data, error, loading, refresh } = usePolling(() => api.runs(100), 4000);
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState({
    experiments: 8,
    model: "echo",
    provider: "",
    seed: 1,
    max_parallel: 4,
    n_events: 200000,
    symbol: "SYNTH",
    data_source: "synthetic" as "synthetic" | "crypto_l2",
    data_path: "",
    tick_size: 0.01,
    sandbox: false,
  });

  useEffect(() => {
    api.datasets().then(setDatasets).catch(() => setDatasets([]));
  }, []);

  async function onStart(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const job = await api.startResearch({
        experiments: form.experiments,
        model: form.model,
        provider: form.provider || null,
        seed: form.seed,
        max_parallel: form.max_parallel,
        n_events: form.n_events,
        symbol: form.symbol,
        data_source: form.data_source,
        data_path: form.data_source === "crypto_l2" ? form.data_path : null,
        tick_size: form.tick_size,
        sandbox: form.sandbox,
      });
      setMsg(`Started research job ${job.id} → /jobs`);
      refresh();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(id: number) {
    if (!confirm(`Delete run #${id} and all its experiments/evaluations?`)) return;
    await api.deleteRun(id);
    refresh();
  }

  if (loading && !data) return <div className="empty">Loading runs…</div>;
  if (error && !data) return <div className="error-banner">{error}</div>;
  if (!data) return null;

  const running = data.filter((r) => r.status === "running").length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Runs</h1>
          <p>Start research experiments and manage persisted runs.</p>
        </div>
        <Link className="btn" to="/jobs">
          View jobs
        </Link>
      </div>
      {error && <div className="error-banner">{error}</div>}

      <div className="panel">
        <h2 className="panel-title">Start research run</h2>
        <form onSubmit={onStart}>
          <div className="form-grid">
            <div className="form-field">
              <label>Model</label>
              <input
                value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
                placeholder="echo | gpt-4o | qwen2.5-coder:7b"
              />
            </div>
            <div className="form-field">
              <label>Provider (optional)</label>
              <input
                value={form.provider}
                onChange={(e) => setForm({ ...form, provider: e.target.value })}
                placeholder="echo|ollama|openai|anthropic"
              />
            </div>
            <div className="form-field">
              <label>Experiments</label>
              <input
                type="number"
                value={form.experiments}
                onChange={(e) => setForm({ ...form, experiments: Number(e.target.value) })}
              />
            </div>
            <div className="form-field">
              <label>Max parallel</label>
              <input
                type="number"
                value={form.max_parallel}
                onChange={(e) => setForm({ ...form, max_parallel: Number(e.target.value) })}
              />
            </div>
            <div className="form-field">
              <label>Seed</label>
              <input
                type="number"
                value={form.seed}
                onChange={(e) => setForm({ ...form, seed: Number(e.target.value) })}
              />
            </div>
            <div className="form-field">
              <label>Symbol</label>
              <input
                value={form.symbol}
                onChange={(e) => setForm({ ...form, symbol: e.target.value })}
              />
            </div>
            <div className="form-field">
              <label>Data source</label>
              <select
                value={form.data_source}
                onChange={(e) => {
                  const data_source = e.target.value as "synthetic" | "crypto_l2";
                  setForm({
                    ...form,
                    data_source,
                    tick_size: data_source === "crypto_l2" ? 0.1 : 0.01,
                    symbol:
                      data_source === "crypto_l2" && form.symbol === "SYNTH"
                        ? "BTC-USDT"
                        : form.symbol,
                  });
                }}
              >
                <option value="synthetic">synthetic</option>
                <option value="crypto_l2">crypto_l2</option>
              </select>
            </div>
            {form.data_source === "crypto_l2" ? (
              <div className="form-field">
                <label>Dataset</label>
                <select
                  value={form.data_path}
                  onChange={(e) => setForm({ ...form, data_path: e.target.value })}
                  required
                >
                  <option value="">Select dataset…</option>
                  {datasets.map((d) => (
                    <option key={d.name} value={d.name}>
                      {d.name} ({d.n_events.toLocaleString()} events)
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="form-field">
                <label>Synthetic events</label>
                <input
                  type="number"
                  value={form.n_events}
                  onChange={(e) => setForm({ ...form, n_events: Number(e.target.value) })}
                />
              </div>
            )}
            <div className="form-field">
              <label>Tick size</label>
              <input
                type="number"
                step="0.01"
                value={form.tick_size}
                onChange={(e) => setForm({ ...form, tick_size: Number(e.target.value) })}
              />
            </div>
            <div className="form-field">
              <label>Sandbox</label>
              <select
                value={form.sandbox ? "1" : "0"}
                onChange={(e) => setForm({ ...form, sandbox: e.target.value === "1" })}
              >
                <option value="0">off</option>
                <option value="1">on</option>
              </select>
            </div>
          </div>
          <div className="form-actions">
            <button className="btn primary" type="submit" disabled={busy}>
              {busy ? "Starting…" : "Start run"}
            </button>
            {msg && <span className="toast">{msg}</span>}
          </div>
        </form>
      </div>

      <div className="grid-stats">
        <div className="stat">
          <div className="stat-label">Total</div>
          <div className="stat-value">{data.length}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Running</div>
          <div className="stat-value running">{running}</div>
        </div>
      </div>

      <div className="panel">
        {data.length === 0 ? (
          <div className="empty">No runs yet.</div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Run</th>
                <th>Created</th>
                <th>Symbol</th>
                <th>Model</th>
                <th>Status</th>
                <th>Experiments</th>
                <th>Survivors</th>
                <th>Survival</th>
                <th>PBO</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/runs/${r.id}`}>#{r.id}</Link>
                  </td>
                  <td>{fmtTime(r.created_at)}</td>
                  <td className="mono">{r.symbol}</td>
                  <td className="mono">{r.model_name}</td>
                  <td>
                    <span className={`pill ${r.status === "running" ? "running" : "muted"}`}>
                      {r.status}
                    </span>
                  </td>
                  <td className="mono">{r.n_experiments}</td>
                  <td className="mono">{r.n_survivors}</td>
                  <td className="mono">{fmtPct(r.survival_rate)}</td>
                  <td className="mono">{fmtNum(r.pbo)}</td>
                  <td>
                    <button
                      type="button"
                      className="btn danger sm"
                      onClick={() => onDelete(r.id)}
                      disabled={r.status === "running"}
                    >
                      delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
