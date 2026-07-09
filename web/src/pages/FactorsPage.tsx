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
import { fmtNum, fmtTime } from "../format";
import { usePolling } from "../hooks/usePolling";

export function FactorsPage() {
  const { data, error, loading } = usePolling(() => api.factors(100), 5000);

  if (loading && !data) return <div className="empty">Loading survivors…</div>;
  if (error && !data) return <div className="error-banner">{error}</div>;
  if (!data) return null;

  const chartData = data.slice(0, 12).map((f) => ({
    name: f.strategy_name.length > 12 ? `${f.strategy_name.slice(0, 10)}…` : f.strategy_name,
    sharpe: Math.round(f.holdout_sharpe * 1000) / 1000,
  }));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Survivors</h1>
          <p>
            Strategies that beat baselines on holdout, clear FDR, and pass deflated Sharpe ≥ 0.95.
          </p>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}

      <div className="grid-stats">
        <div className="stat">
          <div className="stat-label">Survivors</div>
          <div className="stat-value ok">{data.length}</div>
        </div>
      </div>

      {data.length > 0 && (
        <div className="panel">
          <h2 className="panel-title">Holdout Sharpe (top)</h2>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} layout="vertical" margin={{ left: 24 }}>
                <CartesianGrid stroke="#243040" strokeDasharray="3 3" />
                <XAxis type="number" stroke="#8b9aab" fontSize={12} />
                <YAxis type="category" dataKey="name" stroke="#8b9aab" fontSize={11} width={90} />
                <Tooltip
                  contentStyle={{
                    background: "#121a22",
                    border: "1px solid #334155",
                    borderRadius: 8,
                  }}
                />
                <Bar dataKey="sharpe" fill="#4ade80" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="panel">
        {data.length === 0 ? (
          <div className="empty">No survivors yet — honest harness, empty shelf.</div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Symbol</th>
                <th>Holdout SR</th>
                <th>DSR</th>
                <th>Adj. p</th>
                <th>Max DD</th>
                <th>Hypothesis</th>
                <th>Run</th>
              </tr>
            </thead>
            <tbody>
              {data.map((f) => (
                <tr key={f.id}>
                  <td>
                    <Link to={`/factors/${f.id}`}>{f.strategy_name}</Link>
                  </td>
                  <td className="mono">{f.symbol}</td>
                  <td className="mono">{fmtNum(f.holdout_sharpe)}</td>
                  <td className="mono">{fmtNum(f.deflated_sr)}</td>
                  <td className="mono">{fmtNum(f.adjusted_pvalue)}</td>
                  <td className="mono">{fmtNum(f.max_drawdown)}</td>
                  <td>
                    <div className="hypothesis">
                      {(f.hypothesis || "—").slice(0, 100)}
                      {(f.hypothesis || "").length > 100 ? "…" : ""}
                    </div>
                  </td>
                  <td>
                    <Link to={`/runs/${f.run_id}`}>#{f.run_id}</Link>
                    <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                      {fmtTime(f.created_at)}
                    </div>
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
