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
  const { data, error, loading } = usePolling(() => api.datasets(), 4000);

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
          <p>Recorded OKX / crypto L2 segments under the configured data root.</p>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}

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
          <div className="stat-value mono">{data.reduce((a, d) => a + d.n_events, 0).toLocaleString()}</div>
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
          <div className="empty">
            No parquet/csv under data/raw yet. Try{" "}
            <span className="mono">qra fetch-okx-long data/raw/okx_btc …</span>
          </div>
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
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
