import type { components } from './schema';

type Schemas = components['schemas'];

export type RunStatus = Schemas['RunSummary']['status'];
export type Verdict = NonNullable<Schemas['RunSummary']['verdict']>;
export type RunOptions = Schemas['RunOptions'];
export type CreateRunRequest = Schemas['CreateRunRequest'];
export type CreateRunResponse = Schemas['CreateRunResponse'];
export type RunError = Schemas['RunError'];
export type RunSummary = Schemas['RunSummary'];
export type RunProgress = Schemas['RunProgress'];
export type RunCaseSummary = Schemas['RunCaseSummary'];
export type RunDetail = Schemas['RunDetail'];
export type RunListResponse = Schemas['RunListResponse'];
export type CancelRunResponse = Schemas['CancelRunResponse'];
export type ToolCallSummary = Schemas['ReportToolCall'];
export type TestStepResult = Schemas['ReportStep'];
export type AssertionResult = Schemas['ReportAssertion'];
export type TestCaseResult = Schemas['ReportCase'];
export type ArtifactView = Schemas['ArtifactView'];
export type ArtifactKind = ArtifactView['kind'];
export type RunReport = Schemas['RunReport'];
export type ApiErrorEnvelope = Schemas['ApiErrorEnvelope'];

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
