import { Fragment, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { fmtNum, fmtPct, fmtTime } from "../format";
import { usePolling } from "../hooks/usePolling";

export function RunDetailPage() {
  const { id = "" } = useParams();
  const runId = Number(id);
  const { data, error, loading } = usePolling(
    () => api.run(runId),
    4000,
    Number.isFinite(runId) && runId > 0,
  );
  const { data: experiments, error: expError } = usePolling(
    () => api.experiments(runId),
    4000,
    Number.isFinite(runId) && runId > 0,
  );
  const [openCode, setOpenCode] = useState<number | null>(null);

  if (!Number.isFinite(runId)) return <div className="error-banner">Invalid run id</div>;
  if (loading && !data) return <div className="empty">Loading run #{runId}…</div>;
  if (error && !data) return <div className="error-banner">{error}</div>;
  if (!data?.run) return <div className="error-banner">Run not found</div>;

  const { run, evaluations, usage } = data;

  return (
    <>
      <Link className="back-link" to="/runs">
        ← Runs
      </Link>
      <div className="page-head">
        <div>
          <h1>
            Run #{run.id} · {run.symbol}
          </h1>
          <p>
            {run.model_provider}/{run.model_name} · seed {run.seed} · {fmtTime(run.created_at)}
          </p>
        </div>
        <span className={`pill ${run.status === "running" ? "running" : "muted"}`}>
          {run.status}
        </span>
      </div>
      {(error || expError) && <div className="error-banner">{error || expError}</div>}

      <div className="meta-row">
        <span>
          PBO <strong className="mono">{fmtNum(run.pbo)}</strong>
        </span>
        <span>
          Survivors{" "}
          <strong className="mono">
            {run.n_survivors}/{run.n_experiments}
          </strong>
        </span>
        <span>
          Survival <strong className="mono">{fmtPct(run.survival_rate)}</strong>
        </span>
        <span>
          Best baseline SR <strong className="mono">{fmtNum(run.best_baseline_sharpe)}</strong>
        </span>
        <span>
          Tokens <strong className="mono">{(usage.p + usage.c).toLocaleString()}</strong>
        </span>
        <span>
          Cost <strong className="mono">${fmtNum(usage.cost, 4)}</strong>
        </span>
        <span>
          LLM calls <strong className="mono">{usage.calls}</strong>
        </span>
      </div>

      <div className="panel">
        <h2 className="panel-title">Holdout evaluations</h2>
        {evaluations.length === 0 ? (
          <div className="empty">
            {run.status === "running"
              ? "Evaluation pending — run still in progress."
              : "No evaluations recorded."}
          </div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Holdout SR</th>
                <th>Return</th>
                <th>Max DD</th>
                <th>DSR</th>
                <th>Adj. p</th>
                <th>WF +</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {evaluations.map((e) => (
                <tr key={e.id}>
                  <td>
                    {e.survived ? (
                      <Link to={`/factors/${e.id}`}>{e.strategy_name}</Link>
                    ) : (
                      e.strategy_name
                    )}
                  </td>
                  <td className="mono">{fmtNum(e.holdout_sharpe)}</td>
                  <td className="mono">{fmtNum(e.holdout_return)}</td>
                  <td className="mono">{fmtNum(e.max_drawdown)}</td>
                  <td className="mono">{fmtNum(e.deflated_sr)}</td>
                  <td className="mono">{fmtNum(e.adjusted_pvalue)}</td>
                  <td className="mono">{fmtPct(e.wf_frac_positive)}</td>
                  <td>
                    <span className={`pill ${e.survived ? "ok" : "fail"}`}>
                      {e.survived ? "survived" : "failed"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <h2 className="panel-title">Experiments</h2>
        {!experiments || experiments.length === 0 ? (
          <div className="empty">No experiment rows for this run.</div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                <th>Strategy</th>
                <th>Val SR</th>
                <th>Submitted</th>
                <th>Steps</th>
                <th>Hypothesis</th>
                <th>Code</th>
              </tr>
            </thead>
            <tbody>
              {experiments.map((x) => (
                <Fragment key={x.id}>
                  <tr>
                    <td className="mono">{x.experiment_id}</td>
                    <td>{x.strategy_name}</td>
                    <td className="mono">{fmtNum(x.val_sharpe)}</td>
                    <td>
                      <span className={`pill ${x.submitted ? "ok" : "muted"}`}>
                        {x.submitted ? "yes" : "no"}
                      </span>
                    </td>
                    <td className="mono">{x.steps}</td>
                    <td>
                      <div className="hypothesis">
                        {(x.hypothesis || "").slice(0, 160)}
                        {(x.hypothesis || "").length > 160 ? "…" : ""}
                      </div>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="pill muted"
                        style={{ cursor: "pointer", border: "none" }}
                        onClick={() => setOpenCode(openCode === x.id ? null : x.id)}
                      >
                        {openCode === x.id ? "hide" : "view"}
                      </button>
                    </td>
                  </tr>
                  {openCode === x.id && (
                    <tr>
                      <td colSpan={7}>
                        <pre className="code-block">{x.strategy_code || "(empty)"}</pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
