// Shared types mirroring the AOIE FastAPI control-plane contract.

export type Outcome = "VERIFIED" | "FAILED" | "PARTIAL" | "UNKNOWN";
export type VerdictStatus = "SATISFIED" | "VIOLATED" | "CONFLICT" | "UNKNOWN";
export type VerifierStatus = "PASS" | "FAIL" | "INCONCLUSIVE";
export type VerifierType =
  | "api"
  | "database"
  | "dom"
  | "network"
  | "visual"
  | "semantic";

export interface CatalogTask {
  task_id: string;
  description: string;
  collection: string;
  record_id: string;
  scenarios: string[];
}

export interface Catalog {
  tasks: CatalogTask[];
  scenarios: string[];
}

export interface RunSummary {
  run_id: string;
  task_id: string;
  adapter_name: string;
  scenario: string | null;
  agent_claimed_success: boolean;
  final_outcome: string;
  failure_class: string | null;
  false_completion: boolean;
  confidence: number;
  recovered: boolean;
  recovery_attempts: number;
  started_at: string | null;
  ended_at: string | null;
}

export interface AgentClaim {
  claimed_success: boolean;
  message: string | null;
}

export interface VerifierResult {
  verifier_type: VerifierType;
  postcondition_ref: string;
  status: VerifierStatus;
  expected: unknown;
  observed: unknown;
  confidence: number;
  latency_ms: number;
  evidence_id: string | null;
  note: string | null;
}

export interface ReconciledVerdict {
  postcondition_ref: string;
  verdict: VerdictStatus;
  confidence: number;
  conflict: boolean;
  contributing: VerifierResult[];
  reason: string;
}

export interface TaskOutcome {
  outcome: Outcome;
  failure_class: string | null;
  confidence: number;
  satisfied_weight: number;
  total_weight: number;
  reason: string;
  verdicts: ReconciledVerdict[];
  agent_claim?: AgentClaim;
}

// TaskOutcome.false_completion is a plain (non-serialized) property on the
// backend, so derive it here: claimed success that AOIE did not verify.
export function isFalseCompletion(claimed: boolean, outcome: Outcome): boolean {
  return claimed && outcome !== "VERIFIED";
}

export interface Evidence {
  verifier_type: VerifierType;
  source: string;
  expected_state: unknown;
  observed_state: unknown;
  comparison: Record<string, unknown>;
  confidence: number;
  id: string;
  content_hash: string;
  [key: string]: unknown;
}

export interface VerificationReport {
  verdicts: ReconciledVerdict[];
  results: VerifierResult[];
  evidence: Evidence[];
  total_latency_ms: number;
}

export interface Round {
  round_no: number;
  report: VerificationReport;
  outcome: TaskOutcome;
}

export interface RecoveryAttempt {
  attempt_no: number;
  strategy: string;
  reason: string;
  idempotency_safe: boolean;
  executed: boolean;
  outcome_after: string | null;
}

export interface RecoveryHistory {
  attempts: RecoveryAttempt[];
  count?: number;
}

export interface Transition {
  from_state: string;
  to_state: string;
  at: string;
  note: string;
}

export interface TraceEvent {
  span_id: string;
  parent_id: string | null;
  kind: string;
  name: string;
  attributes: Record<string, unknown>;
  ts: string;
}

export interface ExecutionTrace {
  run_id: string;
  events: TraceEvent[];
}

export interface RunResult {
  run_id: string;
  task_id: string;
  adapter_name: string;
  agent_claim: AgentClaim;
  initial_outcome: TaskOutcome;
  final_outcome: TaskOutcome;
  rounds: Round[];
  recovery_history: RecoveryHistory;
  evidence: Evidence[];
  transitions: Transition[];
  trace: ExecutionTrace;
  started_at: string;
  ended_at: string | null;
  error: string | null;
}

export interface Metrics {
  total_runs: number;
  apparent_success_rate?: number;
  verified_success_rate?: number;
  false_completion_rate?: number | null;
  outcome_integrity?: number;
  recovered_runs?: number;
  outcome_counts?: Record<string, number>;
  failure_class_counts?: Record<string, number>;
}

// Benchmark metrics are a superset of Metrics with a few extra fields.
export interface BenchmarkMetrics extends Omit<Metrics, "total_runs"> {
  total_runs?: number;
  total_tasks?: number;
  detection_rate?: number;
  recovery_success_rate?: number;
  mean_recovery_attempts?: number;
  mean_verification_latency_ms?: number;
  aoie_accuracy?: number;
}

export interface BenchRecord {
  task_id: string;
  scenario: string;
  adapter_name: string;
  ground_truth: string;
  agent_claimed_success: boolean;
  aoie_outcome: string;
  failure_class: string | null;
  false_completion: boolean;
  recovered: boolean;
  recovery_attempts: number;
  verification_latency_ms: number;
  caught: boolean;
  correct: boolean;
}

export interface BenchmarkLatest {
  generated_at: string;
  metrics: BenchmarkMetrics;
  records: BenchRecord[];
}
