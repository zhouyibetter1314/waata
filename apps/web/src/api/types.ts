export type RunStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'errored'
  | 'cancelled';
export type Verdict = 'passed' | 'failed' | 'blocked' | 'inconclusive';

export interface RunOptions {
  headless?: boolean;
  max_steps_per_case?: number;
}

export interface CreateRunRequest {
  target_url: string;
  goal: string;
  expected_behavior: string;
  credential_ref?: string | null;
  options?: RunOptions;
}

export interface CreateRunResponse {
  run_id: string;
  status: 'queued';
  created_at: string;
}

export interface RunError {
  code: string;
  message: string;
  retryable?: boolean;
  details?: Record<string, unknown> | null;
}

export interface RunSummary {
  run_id: string;
  target_url: string;
  goal: string;
  status: RunStatus;
  verdict: Verdict | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface RunProgress {
  total_cases: number | null;
  completed_cases: number;
}

export interface RunCaseSummary {
  passed: number;
  failed: number;
  blocked: number;
  inconclusive: number;
}

export interface RunDetail extends RunSummary {
  expected_behavior: string;
  progress: RunProgress;
  summary: RunCaseSummary | null;
  error: RunError | null;
  cancellation_requested: boolean;
}

export interface RunListResponse {
  items: RunSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface CancelRunResponse {
  run_id: string;
  status: RunStatus;
  cancellation_requested: boolean;
}

export interface ToolCallSummary {
  tool_call_id: string;
  tool: string;
  success: boolean;
  duration_ms: number;
  error_code: string | null;
  evidence_ids: string[];
}

export interface TestStepResult {
  step_id: string;
  summary: string;
  tool_calls: ToolCallSummary[];
}

export interface AssertionResult {
  assertion_id: string;
  expected: unknown;
  actual: unknown;
  passed: boolean | null;
  evidence_ids: string[];
}

export interface TestCaseResult {
  case_id: string;
  name: string;
  preconditions: string[];
  expected_behavior: string;
  verdict: Verdict;
  reason: string | null;
  steps: TestStepResult[];
  assertions: AssertionResult[];
}

export type ArtifactKind =
  | 'observation'
  | 'screenshot'
  | 'playwright_trace'
  | 'test_report';

export interface ArtifactView {
  artifact_id: string;
  run_id: string;
  case_id: string | null;
  step_id: string | null;
  tool_call_id: string | null;
  kind: ArtifactKind;
  mime_type: string;
  captured_at: string;
  size_bytes: number;
  url: string;
  expires_at: string | null;
}

export interface RunReport {
  run_id: string;
  status: RunStatus;
  verdict: Verdict | null;
  error: RunError | null;
  execution: {
    target_url: string;
    max_steps_per_case: number;
    max_browser_actions_per_run: number;
    max_test_cases: number;
    timeout_seconds: number;
  };
  cases: TestCaseResult[];
  artifacts: ArtifactView[];
  langfuse_trace_id: string | null;
}

export interface PublishedEvent {
  schema_version: 1;
  event_id: string;
  run_id: string;
  sequence: number;
  type: string;
  timestamp: string;
  case_id: string | null;
  step_id: string | null;
  payload: Record<string, unknown>;
}

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    request_id: string;
  };
}
