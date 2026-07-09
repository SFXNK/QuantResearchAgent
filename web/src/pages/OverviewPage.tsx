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
import { fmtNum, fmtPct, fmtTime } from "../format";
import { usePolling } from "../hooks/usePolling";

export function OverviewPage() {
  const { data, error, loading } = usePolling(() => api.overview(), 4000);

  if (loading && !data) return <div className="empty">Loading overview…</div>;
  if (error && !data) return <div className="error-banner">{error}</div>;
  if (!data) return null;

  const chartData = data.recent_runs
    .slice()
    .reverse()
    .map((r) => ({
      name: `#${r.id}`,
      survivors: r.n_survivors ?? 0,
      rate: Math.round((r.survival_rate ?? 0) * 1000) / 10,
    }));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Overview</h1>
          <p>Live snapshot of capture activity, research runs, and surviving strategies.</p>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}

      <div className="grid-stats">
        <div className="stat">
          <div className="stat-label">Active capture</div>
          <div className="stat-value accent">{data.active_datasets}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Datasets</div>
          <div className="stat-value">{data.datasets}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Runs running</div>
          <div className="stat-value running">{data.running}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Total runs</div>
          <div className="stat-value">{data.runs}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Survivors</div>
          <div className="stat-value ok">{data.survivors}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Evaluations</div>
          <div className="stat-value">{data.evaluations}</div>
        </div>
      </div>

      <div className="panel-grid">
        <div className="panel">
          <h2 className="panel-title">Recent runs — survivors</h2>
          {chartData.length === 0 ? (
            <div className="empty">No runs yet. Run `qra research` first.</div>
          ) : (
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid stroke="#243040" strokeDasharray="3 3" />
                  <XAxis dataKey="name" stroke="#8b9aab" fontSize={12} />
                  <YAxis stroke="#8b9aab" fontSize={12} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      background: "#121a22",
                      border: "1px solid #334155",
                      borderRadius: 8,
                    }}
                  />
                  <Bar dataKey="survivors" fill="#3dd6c6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="panel">
          <h2 className="panel-title">Latest runs</h2>
          {data.recent_runs.length === 0 ? (
            <div className="empty">No runs in the store.</div>
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Symbol</th>
                  <th>Status</th>
                  <th>Survivors</th>
                  <th>PBO</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_runs.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link to={`/runs/${r.id}`}>#{r.id}</Link>
                    </td>
                    <td className="mono">{r.symbol}</td>
                    <td>
                      <span className={`pill ${r.status === "running" ? "running" : "muted"}`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="mono">
                      {r.n_survivors}/{r.n_experiments}
                    </td>
                    <td className="mono">{fmtNum(r.pbo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="panel">
        <h2 className="panel-title">Top survivors</h2>
        {data.top_survivors.length === 0 ? (
          <div className="empty">No strategies have survived OOS evaluation yet.</div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Symbol</th>
                <th>Holdout SR</th>
                <th>DSR</th>
                <th>Adj. p</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {data.top_survivors.map((f) => (
                <tr key={f.id}>
                  <td>
                    <Link to={`/factors/${f.id}`}>{f.strategy_name}</Link>
                  </td>
                  <td className="mono">{f.symbol}</td>
                  <td className="mono">{fmtNum(f.holdout_sharpe)}</td>
                  <td className="mono">{fmtNum(f.deflated_sr)}</td>
                  <td className="mono">{fmtNum(f.adjusted_pvalue)}</td>
                  <td>{fmtTime(f.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p style={{ marginTop: "0.75rem", fontSize: "0.85rem" }}>
          <Link to="/factors">Browse all survivors →</Link>
          {" · survival rate legend: "}
          <span className="mono">{fmtPct(data.survivors / Math.max(data.evaluations, 1))}</span> of
          evaluations
        </p>
      </div>
    </>
  );
}
