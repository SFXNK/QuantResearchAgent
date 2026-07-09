export type RunStatus = "running" | "completed";

export interface Run {
  id: number;
  created_at: number;
  seed: number;
  symbol: string;
  model_provider: string;
  model_name: string;
  n_experiments: number;
  dataset_fingerprint: string | null;
  pbo: number | null;
  n_survivors: number;
  survival_rate: number;
  best_baseline_sharpe: number;
  config_json?: string;
  status: RunStatus;
}

export interface Evaluation {
  id: number;
  run_id: number;
  experiment_id: number;
  strategy_name: string;
  holdout_sharpe: number;
  holdout_return: number;
  max_drawdown: number;
  pvalue: number;
  adjusted_pvalue: number;
  deflated_sr: number;
  beats_baselines: number;
  significant: number;
  survived: number;
  wf_mean_sharpe: number;
  wf_frac_positive: number;
}

export interface Experiment {
  id: number;
  run_id: number;
  experiment_id: number;
  hypothesis: string;
  strategy_name: string;
  strategy_code: string;
  val_sharpe: number;
  submitted: number;
  steps: number;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface Factor extends Evaluation {
  symbol: string;
  model_name: string;
  created_at: number;
  hypothesis: string | null;
  strategy_code: string | null;
  val_sharpe: number | null;
}

export interface UsageTotals {
  p: number;
  c: number;
  cost: number;
  latency: number;
  cached: number;
  calls: number;
}

export interface DatasetSummary {
  name: string;
  path: string;
  kind: string;
  n_files: number;
  n_events: number;
  size_bytes: number;
  latest_mtime: number;
  ts_min: number | null;
  ts_max: number | null;
  active: boolean;
}

export interface SegmentInfo {
  name: string;
  path: string;
  size_bytes: number;
  mtime: number;
  n_events: number;
  ts_min: number | null;
  ts_max: number | null;
}

export interface DatasetDetail extends DatasetSummary {
  segments: SegmentInfo[];
}

export interface Overview {
  runs: number;
  running: number;
  survivors: number;
  evaluations: number;
  datasets: number;
  active_datasets: number;
  recent_runs: Run[];
  top_survivors: Factor[];
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<{ ok: boolean }>("/api/health"),
  overview: () => get<Overview>("/api/overview"),
  runs: (limit = 50) => get<Run[]>(`/api/runs?limit=${limit}`),
  run: (id: number) =>
    get<{ run: Run; evaluations: Evaluation[]; usage: UsageTotals }>(`/api/runs/${id}`),
  experiments: (id: number) => get<Experiment[]>(`/api/runs/${id}/experiments`),
  factors: (limit = 100) => get<Factor[]>(`/api/factors?limit=${limit}`),
  factor: (id: number) => get<Factor>(`/api/factors/${id}`),
  datasets: () => get<DatasetSummary[]>("/api/data/datasets"),
  dataset: (name: string) => get<DatasetDetail>(`/api/data/datasets/${encodeURIComponent(name)}`),
};
