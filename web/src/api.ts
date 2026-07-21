export type RunStatus = "running" | "completed";
export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export type JobKind = "record" | "research";

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

export interface Job {
  id: string;
  kind: JobKind;
  status: JobStatus;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  params: Record<string, unknown>;
  progress: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: string | null;
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
  jobs?: Job[];
}

export interface RecordRequest {
  inst_id: string;
  name?: string;
  mode: "long" | "short";
  segment_minutes?: number;
  total_minutes?: number | null;
  duration_s?: number;
  qty_scale?: number;
  channel?: string;
}

export interface ResearchRequest {
  experiments: number;
  model: string;
  provider?: string | null;
  base_url?: string | null;
  api_key_env?: string | null;
  seed: number;
  max_parallel: number;
  n_events: number;
  symbol: string;
  data_source: "synthetic" | "crypto_l2";
  data_path?: string | null;
  tick_size: number;
  sandbox: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined });
const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const del = <T>(path: string) => request<T>(path, { method: "DELETE" });

export const api = {
  health: () => get<{ ok: boolean }>("/api/health"),
  overview: () => get<Overview>("/api/overview"),
  runs: (limit = 50) => get<Run[]>(`/api/runs?limit=${limit}`),
  run: (id: number) =>
    get<{ run: Run; evaluations: Evaluation[]; usage: UsageTotals }>(`/api/runs/${id}`),
  experiments: (id: number) => get<Experiment[]>(`/api/runs/${id}/experiments`),
  deleteRun: (id: number) => del<{ ok: boolean }>(`/api/runs/${id}`),
  factors: (limit = 100) => get<Factor[]>(`/api/factors?limit=${limit}`),
  factor: (id: number) => get<Factor>(`/api/factors/${id}`),
  setSurvived: (id: number, survived: boolean) =>
    patch<Factor>(`/api/factors/${id}`, { survived }),
  deleteFactor: (id: number) => del<{ ok: boolean }>(`/api/factors/${id}`),
  datasets: () => get<DatasetSummary[]>("/api/data/datasets"),
  dataset: (name: string) => get<DatasetDetail>(`/api/data/datasets/${encodeURIComponent(name)}`),
  deleteDataset: (name: string) =>
    del<{ ok: boolean }>(`/api/data/datasets/${encodeURIComponent(name)}`),
  deleteSegment: (name: string, filename: string) =>
    del<{ ok: boolean }>(
      `/api/data/datasets/${encodeURIComponent(name)}/segments/${encodeURIComponent(filename)}`,
    ),
  jobs: (limit = 50) => get<Job[]>(`/api/jobs?limit=${limit}`),
  job: (id: string) => get<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => post<Job>(`/api/jobs/${id}/cancel`),
  startRecord: (body: RecordRequest) => post<Job>("/api/actions/record", body),
  startResearch: (body: ResearchRequest) => post<Job>("/api/actions/research", body),
};
