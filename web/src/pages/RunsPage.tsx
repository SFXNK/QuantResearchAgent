import { Link } from "react-router-dom";
import { api } from "../api";
import { fmtNum, fmtPct, fmtTime } from "../format";
import { usePolling } from "../hooks/usePolling";

export function RunsPage() {
  const { data, error, loading } = usePolling(() => api.runs(100), 4000);

  if (loading && !data) return <div className="empty">Loading runs…</div>;
  if (error && !data) return <div className="error-banner">{error}</div>;
  if (!data) return null;

  const running = data.filter((r) => r.status === "running").length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Runs</h1>
          <p>Research experiments persisted in the SQLite store.</p>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}

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
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
