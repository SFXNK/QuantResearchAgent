import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import { fmtBytes, fmtNum, fmtTime, relativeAge } from "../format";
import { usePolling } from "../hooks/usePolling";

export function DataPage() {
  const { data, error, loading, refresh } = usePolling(() => api.datasets(), 4000);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState({
    inst_id: "BTC-USDT",
    name: "btc_usdt",
    mode: "long" as "long" | "short",
    segment_minutes: 10,
    total_minutes: "" as string,
    duration_s: 60,
    qty_scale: 1e6,
  });

  async function onRecord(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const job = await api.startRecord({
        inst_id: form.inst_id,
        name: form.name || undefined,
        mode: form.mode,
        segment_minutes: form.segment_minutes,
        total_minutes: form.total_minutes === "" ? null : Number(form.total_minutes),
        duration_s: form.duration_s,
        qty_scale: form.qty_scale,
      });
      setMsg(`Started record job ${job.id} → /jobs`);
      refresh();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(name: string) {
    if (!confirm(`Delete dataset "${name}" and all its files?`)) return;
    await api.deleteDataset(name);
    refresh();
  }

  if (loading && !data) return <div className="empty">Scanning data/raw…</div>;
  if (error && !data) return <div className="error-banner">{error}</div>;
  if (!data) return null;

  const chartData = data.map((d) => ({
    name: d.name.length > 14 ? `${d.name.slice(0, 12)}…` : d.name,
    events: d.n_events,
  }));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Data Capture</h1>
          <p>Record OKX streams and manage parquet datasets under data/raw.</p>
        </div>
        <Link className="btn" to="/jobs">
          View jobs
        </Link>
      </div>
      {error && <div className="error-banner">{error}</div>}

      <div className="panel">
        <h2 className="panel-title">Start OKX recording</h2>
        <form onSubmit={onRecord}>
          <div className="form-grid">
            <div className="form-field">
              <label>Instrument</label>
              <input
                value={form.inst_id}
                onChange={(e) => setForm({ ...form, inst_id: e.target.value })}
              />
            </div>
            <div className="form-field">
              <label>Dataset name</label>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="btc_usdt"
              />
            </div>
            <div className="form-field">
              <label>Mode</label>
              <select
                value={form.mode}
                onChange={(e) =>
                  setForm({ ...form, mode: e.target.value as "long" | "short" })
                }
              >
                <option value="long">Long (segmented)</option>
                <option value="short">Short (fixed duration)</option>
              </select>
            </div>
            <div className="form-field">
              <label>Qty scale</label>
              <input
                type="number"
                value={form.qty_scale}
                onChange={(e) => setForm({ ...form, qty_scale: Number(e.target.value) })}
              />
            </div>
            {form.mode === "long" ? (
              <>
                <div className="form-field">
                  <label>Segment minutes</label>
                  <input
                    type="number"
                    value={form.segment_minutes}
                    onChange={(e) =>
                      setForm({ ...form, segment_minutes: Number(e.target.value) })
                    }
                  />
                </div>
                <div className="form-field">
                  <label>Total minutes (empty = until cancel)</label>
                  <input
                    value={form.total_minutes}
                    onChange={(e) => setForm({ ...form, total_minutes: e.target.value })}
                    placeholder="e.g. 120"
                  />
                </div>
              </>
            ) : (
              <div className="form-field">
                <label>Duration (seconds)</label>
                <input
                  type="number"
                  value={form.duration_s}
                  onChange={(e) => setForm({ ...form, duration_s: Number(e.target.value) })}
                />
              </div>
            )}
          </div>
          <div className="form-actions">
            <button className="btn primary" type="submit" disabled={busy}>
              {busy ? "Starting…" : "Start recording"}
            </button>
            {msg && <span className="toast">{msg}</span>}
          </div>
        </form>
      </div>

      <div className="grid-stats">
        <div className="stat">
          <div className="stat-label">Datasets</div>
          <div className="stat-value">{data.length}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Active</div>
          <div className="stat-value accent">{data.filter((d) => d.active).length}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Total events</div>
          <div className="stat-value mono">
            {data.reduce((a, d) => a + d.n_events, 0).toLocaleString()}
          </div>
        </div>
        <div className="stat">
          <div className="stat-label">Disk</div>
          <div className="stat-value mono">
            {fmtBytes(data.reduce((a, d) => a + d.size_bytes, 0))}
          </div>
        </div>
      </div>

      {data.length > 0 && (
        <div className="panel">
          <h2 className="panel-title">Events by dataset</h2>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid stroke="#243040" strokeDasharray="3 3" />
                <XAxis dataKey="name" stroke="#8b9aab" fontSize={11} />
                <YAxis stroke="#8b9aab" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    background: "#121a22",
                    border: "1px solid #334155",
                    borderRadius: 8,
                  }}
                />
                <Bar dataKey="events" fill="#60a5fa" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="panel">
        <h2 className="panel-title">Datasets</h2>
        {data.length === 0 ? (
          <div className="empty">No parquet/csv under data/raw yet.</div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Files</th>
                <th>Events</th>
                <th>Size</th>
                <th>Latest</th>
                <th>Span</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.name}>
                  <td>
                    <Link to={`/data/${encodeURIComponent(d.name)}`}>{d.name}</Link>
                    <div className="mono" style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                      {d.kind}
                    </div>
                  </td>
                  <td>
                    <span className={`pill ${d.active ? "active" : "muted"}`}>
                      {d.active ? "recording" : "idle"}
                    </span>
                  </td>
                  <td className="mono">{d.n_files}</td>
                  <td className="mono">{d.n_events.toLocaleString()}</td>
                  <td className="mono">{fmtBytes(d.size_bytes)}</td>
                  <td>
                    {relativeAge(d.latest_mtime)}
                    <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                      {fmtTime(d.latest_mtime)}
                    </div>
                  </td>
                  <td className="mono" style={{ fontSize: "0.78rem" }}>
                    {d.ts_min != null && d.ts_max != null
                      ? `${fmtNum((d.ts_max - d.ts_min) / 1e9, 1)}s`
                      : "—"}
                  </td>
                  <td>
                    <button type="button" className="btn danger sm" onClick={() => onDelete(d.name)}>
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
