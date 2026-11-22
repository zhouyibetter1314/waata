import {
  API_BASE,
  encodePathSegment,
  jsonRequest,
  requestJson,
  requestRaw,
} from './client';
import type {
  ArtifactView,
  CancelRunResponse,
  CreateRunRequest,
  CreateRunResponse,
  RunDetail,
  RunListResponse,
  RunReport,
} from './types';

export interface ListRunsOptions {
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
}

export function createRun(value: CreateRunRequest, signal?: AbortSignal) {
  return requestJson<CreateRunResponse>('/test-runs', {
    ...jsonRequest('POST', value),
    signal,
  });
}

export function listRuns(options: ListRunsOptions = {}) {
  const query = new URLSearchParams({
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? 20),
  });
  return requestJson<RunListResponse>(`/test-runs?${query}`, {
    signal: options.signal,
  });
}

export function getRun(runId: string, signal?: AbortSignal) {
  return requestJson<RunDetail>(`/test-runs/${encodePathSegment(runId)}`, {
    signal,
  });
}

export function getRunReport(runId: string, signal?: AbortSignal) {
  return requestJson<RunReport>(
    `/test-runs/${encodePathSegment(runId)}/report`,
    { signal },
  );
}

export function cancelRun(runId: string, signal?: AbortSignal) {
  return requestJson<CancelRunResponse>(
    `/test-runs/${encodePathSegment(runId)}/cancel`,
    {
      method: 'POST',
      signal,
    },
  );
}

export function runEventsUrl(runId: string, after?: number): string {
  const path = `${API_BASE}/test-runs/${encodePathSegment(runId)}/events`;
  return after === undefined
    ? path
    : `${path}?${new URLSearchParams({ after: String(after) })}`;
}

export function artifactUrl(artifactId: string): string {
  return `${API_BASE}/artifacts/${encodePathSegment(artifactId)}`;
}

export function getArtifact(artifactId: string, signal?: AbortSignal) {
  return requestRaw(`/artifacts/${encodePathSegment(artifactId)}`, {
    signal,
    headers: { Accept: '*/*' },
  });
}

export function artifactViewUrl(artifact: Pick<ArtifactView, 'url'>): string {
  return artifact.url;
}
