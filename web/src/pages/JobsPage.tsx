import { Link } from "react-router-dom";
import { api, type Job } from "../api";
import { fmtTime } from "../format";
import { usePolling } from "../hooks/usePolling";

function statusClass(s: string): string {
  if (s === "running") return "running";
  if (s === "completed") return "ok";
  if (s === "failed") return "failed";
  if (s === "queued") return "queued";
  return "cancelled";
}

export function JobsPage() {
  const { data, error, loading, refresh } = usePolling(() => api.jobs(50), 2000);

  async function cancel(id: string) {
    if (!confirm(`Cancel job ${id}?`)) return;
    await api.cancelJob(id);
    refresh();
  }

  if (loading && !data) return <div className="empty">Loading jobs…</div>;
  if (error && !data) return <div className="error-banner">{error}</div>;

  const jobs = data || [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Jobs</h1>
          <p>Background capture and research tasks started from the UI.</p>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}

      <div className="panel">
        {jobs.length === 0 ? (
          <div className="empty">No jobs yet. Start a capture or research run from Data / Runs.</div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>ID</th>
                <th>Kind</th>
                <th>Status</th>
                <th>Created</th>
                <th>Progress</th>
                <th>Result</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j: Job) => (
                <tr key={j.id}>
                  <td className="mono">{j.id}</td>
                  <td className="mono">{j.kind}</td>
                  <td>
                    <span className={`pill ${statusClass(j.status)}`}>{j.status}</span>
                  </td>
                  <td>{fmtTime(j.created_at)}</td>
                  <td className="mono" style={{ fontSize: "0.75rem" }}>
                    {j.kind === "record" && (
                      <>
                        seg {String(j.progress.segments ?? 0)}
                        {j.progress.last_segment ? ` · ${String(j.progress.last_segment)}` : ""}
                      </>
                    )}
                    {j.kind === "research" && (
                      <>
                        {String(j.progress.model ?? "")} / {String(j.progress.source ?? "")}
                      </>
                    )}
                    {j.error && (
                      <div style={{ color: "var(--danger)", maxWidth: 280 }}>
                        {j.error.slice(0, 120)}
                      </div>
                    )}
                  </td>
                  <td className="mono" style={{ fontSize: "0.78rem" }}>
                    {j.result?.run_id != null && (
                      <Link to={`/runs/${j.result.run_id}`}>run #{String(j.result.run_id)}</Link>
                    )}
                    {j.result?.dataset != null && (
                      <Link to={`/data/${encodeURIComponent(String(j.result.dataset))}`}>
                        {String(j.result.dataset)}
                      </Link>
                    )}
                    {j.result?.n_survivors != null && (
                      <div>survivors {String(j.result.n_survivors)}</div>
                    )}
                  </td>
                  <td>
                    {(j.status === "running" || j.status === "queued") && (
                      <button type="button" className="btn danger sm" onClick={() => cancel(j.id)}>
                        cancel
                      </button>
                    )}
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
