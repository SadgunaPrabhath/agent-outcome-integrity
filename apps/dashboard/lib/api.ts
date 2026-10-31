// Typed client for the AOIE FastAPI control-plane.
//
// Base URL comes from NEXT_PUBLIC_API_BASE, defaulting to http://localhost:8000.

import type {
  BenchmarkLatest,
  BenchmarkMetrics,
  Catalog,
  Evidence,
  Metrics,
  RunResult,
  RunSummary,
  VerifierResult,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(
      `Could not reach the AOIE API at ${API_BASE}. Is it running? (${
        err instanceof Error ? err.message : String(err)
      })`,
      0,
    );
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore parse errors */
    }
    throw new ApiError(`${path} failed: ${detail}`, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/healthz"),

  catalog: () => request<Catalog>("/catalog"),

  metrics: () => request<Metrics>("/metrics"),

  listRuns: (limit = 100, offset = 0) =>
    request<{ runs: RunSummary[] }>(`/runs?limit=${limit}&offset=${offset}`).then(
      (d) => d.runs,
    ),

  createRun: (task_id: string, scenario: string) =>
    request<RunResult>("/runs", {
      method: "POST",
      body: JSON.stringify({ task_id, scenario }),
    }),

  getRun: (runId: string) => request<RunResult>(`/runs/${runId}`),

  getVerification: (runId: string) =>
    request<{ results: VerifierResult[] }>(`/runs/${runId}/verification`).then(
      (d) => d.results,
    ),

  getEvidence: (runId: string) =>
    request<{ evidence: Evidence[] }>(`/runs/${runId}/evidence`).then(
      (d) => d.evidence,
    ),

  runBenchmark: () => request<BenchmarkMetrics>("/benchmark/run", { method: "POST" }),

  latestBenchmark: () => request<BenchmarkLatest>("/benchmark/latest"),
};
