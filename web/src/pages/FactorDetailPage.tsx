import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { fmtNum, fmtPct, fmtTime } from "../format";
import { usePolling } from "../hooks/usePolling";

export function FactorDetailPage() {
  const { id = "" } = useParams();
  const evalId = Number(id);
  const navigate = useNavigate();
  const { data, error, loading, refresh } = usePolling(
    () => api.factor(evalId),
    8000,
    Number.isFinite(evalId) && evalId > 0,
  );

  async function toggleSurvived() {
    if (!data) return;
    await api.setSurvived(evalId, !data.survived);
    refresh();
  }

  async function onDelete() {
    if (!confirm("Permanently delete this evaluation?")) return;
    await api.deleteFactor(evalId);
    navigate("/factors");
  }

  if (!Number.isFinite(evalId)) return <div className="error-banner">Invalid factor id</div>;
  if (loading && !data) return <div className="empty">Loading…</div>;
  if (error && !data) return <div className="error-banner">{error}</div>;
  if (!data) return null;

  return (
    <>
      <Link className="back-link" to="/factors">
        ← Survivors
      </Link>
      <div className="page-head">
        <div>
          <h1>{data.strategy_name}</h1>
          <p>
            {data.symbol} · run <Link to={`/runs/${data.run_id}`}>#{data.run_id}</Link> ·{" "}
            {data.model_name} · {fmtTime(data.created_at)}
          </p>
        </div>
        <div className="btn-row">
          <span className={`pill ${data.survived ? "ok" : "fail"}`}>
            {data.survived ? "survived" : "not marked"}
          </span>
          <button type="button" className="btn sm" onClick={toggleSurvived}>
            {data.survived ? "unmark" : "mark survivor"}
          </button>
          <button type="button" className="btn danger sm" onClick={onDelete}>
            delete
          </button>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}

      <div className="grid-stats">
        <div className="stat">
          <div className="stat-label">Holdout Sharpe</div>
          <div className="stat-value ok">{fmtNum(data.holdout_sharpe)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Deflated SR</div>
          <div className="stat-value">{fmtNum(data.deflated_sr)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Adj. p-value</div>
          <div className="stat-value">{fmtNum(data.adjusted_pvalue)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Max drawdown</div>
          <div className="stat-value">{fmtNum(data.max_drawdown)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Holdout return</div>
          <div className="stat-value">{fmtNum(data.holdout_return)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">WF frac+</div>
          <div className="stat-value">{fmtPct(data.wf_frac_positive)}</div>
        </div>
      </div>

      <div className="panel">
        <h2 className="panel-title">Hypothesis</h2>
        <p className="hypothesis" style={{ maxWidth: "none", color: "var(--text)" }}>
          {data.hypothesis || "(no hypothesis text stored)"}
        </p>
        {data.val_sharpe != null && (
          <p style={{ marginTop: "0.75rem", color: "var(--text-muted)", fontSize: "0.85rem" }}>
            Validation Sharpe: <span className="mono">{fmtNum(data.val_sharpe)}</span>
          </p>
        )}
      </div>

      <div className="panel">
        <h2 className="panel-title">Strategy code</h2>
        <pre className="code-block">{data.strategy_code || "(no code stored)"}</pre>
      </div>
    </>
  );
}
