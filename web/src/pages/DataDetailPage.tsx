import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { fmtBytes, fmtTime, relativeAge } from "../format";
import { usePolling } from "../hooks/usePolling";

export function DataDetailPage() {
  const { name = "" } = useParams();
  const { data, error, loading, refresh } = usePolling(
    () => api.dataset(name),
    4000,
    Boolean(name),
  );

  async function onDeleteSegment(filename: string) {
    if (!confirm(`Delete segment ${filename}?`)) return;
    await api.deleteSegment(name, filename);
    refresh();
  }

  async function onDeleteAll() {
    if (!confirm(`Delete entire dataset "${name}"?`)) return;
    await api.deleteDataset(name);
    window.location.href = "/data";
  }

  if (!name) return <div className="error-banner">Missing dataset name</div>;
  if (loading && !data) return <div className="empty">Loading {name}…</div>;
  if (error && !data) return <div className="error-banner">{error}</div>;
  if (!data) return null;

  return (
    <>
      <Link className="back-link" to="/data">
        ← Data Capture
      </Link>
      <div className="page-head">
        <div>
          <h1>{data.name}</h1>
          <p className="mono">{data.path}</p>
        </div>
        <div className="btn-row">
          <span className={`pill ${data.active ? "active" : "muted"}`}>
            {data.active ? "recording" : "idle"}
          </span>
          <button type="button" className="btn danger sm" onClick={onDeleteAll}>
            delete dataset
          </button>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}

      <div className="grid-stats">
        <div className="stat">
          <div className="stat-label">Files</div>
          <div className="stat-value">{data.n_files}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Events</div>
          <div className="stat-value">{data.n_events.toLocaleString()}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Size</div>
          <div className="stat-value">{fmtBytes(data.size_bytes)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Latest write</div>
          <div className="stat-value" style={{ fontSize: "1.1rem" }}>
            {relativeAge(data.latest_mtime)}
          </div>
        </div>
      </div>

      <div className="panel">
        <h2 className="panel-title">Segments</h2>
        <table className="data">
          <thead>
            <tr>
              <th>File</th>
              <th>Events</th>
              <th>Size</th>
              <th>Modified</th>
              <th>ts min</th>
              <th>ts max</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.segments.map((s) => (
              <tr key={s.path}>
                <td className="mono">{s.name}</td>
                <td className="mono">{s.n_events.toLocaleString()}</td>
                <td className="mono">{fmtBytes(s.size_bytes)}</td>
                <td>{fmtTime(s.mtime)}</td>
                <td className="mono" style={{ fontSize: "0.75rem" }}>
                  {s.ts_min ?? "—"}
                </td>
                <td className="mono" style={{ fontSize: "0.75rem" }}>
                  {s.ts_max ?? "—"}
                </td>
                <td>
                  <button
                    type="button"
                    className="btn danger sm"
                    onClick={() => onDeleteSegment(s.name)}
                  >
                    delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
