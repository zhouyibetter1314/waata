import { delay, http, HttpResponse } from 'msw';
import type { CreateRunRequest, RunDetail, RunSummary } from '../api';
import {
  cloneFixture,
  createRunFixture,
  eventStreamFixture,
  runCreatedFixture,
  runDetailFixture,
  runReportFixture,
  toRunSummary,
} from './fixtures';

const details = new Map<string, RunDetail>();
const summaries: RunSummary[] = [];
let nextRunNumber = 2;

function seed(): void {
  details.clear();
  summaries.splice(0);
  nextRunNumber = 2;
  const detail = cloneFixture(runDetailFixture);
  details.set(detail.run_id, detail);
  summaries.push(toRunSummary(detail));
}

seed();

export function resetMockData(): void {
  seed();
}

function error(status: number, code: string, message: string) {
  return HttpResponse.json(
    { error: { code, message, request_id: `mock_${code.toLowerCase()}` } },
    { status },
  );
}

export const handlers = [
  http.post('/api/v1/test-runs', async ({ request }) => {
    const input = (await request.json()) as CreateRunRequest;
    if (input.target_url.includes('forbidden')) {
      return error(403, 'TARGET_NOT_ALLOWED', '测试目标未获授权');
    }
    if (input.target_url.includes('unavailable')) {
      return error(503, 'SERVICE_UNAVAILABLE', '任务服务暂不可用');
    }
    if (!input.goal?.trim() || !input.expected_behavior?.trim()) {
      return error(422, 'VALIDATION_ERROR', '测试目标和预期行为不能为空');
    }
    await delay(80);
    const created = {
      ...cloneFixture(runCreatedFixture),
      run_id: `run_4gaboards_${String(nextRunNumber++).padStart(3, '0')}`,
      created_at: new Date().toISOString(),
    };
    const detail: RunDetail = {
      ...cloneFixture(runDetailFixture),
      run_id: created.run_id,
      target_url: input.target_url,
      goal: input.goal,
      expected_behavior: input.expected_behavior,
      status: 'queued',
      verdict: null,
      progress: { total_cases: null, completed_cases: 0 },
      summary: null,
      error: null,
      cancellation_requested: false,
      created_at: created.created_at,
      started_at: null,
      finished_at: null,
    };
    details.set(detail.run_id, detail);
    summaries.unshift(toRunSummary(detail));
    return HttpResponse.json(created, { status: 202 });
  }),

  http.get('/api/v1/test-runs', ({ request }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get('page') || 1);
    const pageSize = Number(url.searchParams.get('page_size') || 20);
    const start = (page - 1) * pageSize;
    return HttpResponse.json({
      items: summaries.slice(start, start + pageSize),
      page,
      page_size: pageSize,
      total: summaries.length,
    });
  }),

  http.get('/api/v1/test-runs/:runId', ({ params }) => {
    const detail = details.get(String(params.runId));
    return detail
      ? HttpResponse.json(cloneFixture(detail))
      : error(404, 'RUN_NOT_FOUND', '测试任务不存在');
  }),

  http.get('/api/v1/test-runs/:runId/events', async ({ params }) => {
    const runId = String(params.runId);
    const detail = details.get(runId);
    if (!detail) return error(404, 'RUN_NOT_FOUND', '测试任务不存在');
    await delay(750);
    if (!['cancelled', 'errored'].includes(detail.status)) {
      detail.status = 'succeeded';
      detail.verdict = runDetailFixture.verdict;
      detail.progress = cloneFixture(runDetailFixture.progress);
      detail.summary = cloneFixture(runDetailFixture.summary);
      detail.started_at = runDetailFixture.started_at;
      detail.finished_at = runDetailFixture.finished_at;
      const index = summaries.findIndex((item) => item.run_id === runId);
      if (index >= 0) summaries[index] = toRunSummary(detail);
    }
    return new HttpResponse(
      eventStreamFixture.replaceAll(runDetailFixture.run_id, runId),
      {
        headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
      },
    );
  }),

  http.get('/api/v1/test-runs/:runId/report', ({ params }) => {
    const runId = String(params.runId);
    const detail = details.get(runId);
    if (!detail) return error(404, 'RUN_NOT_FOUND', '测试任务不存在');
    if (!['succeeded', 'errored', 'cancelled'].includes(detail.status)) {
      return error(409, 'REPORT_NOT_READY', '测试报告尚未生成');
    }
    if (detail.status === 'cancelled') {
      return error(409, 'REPORT_UNAVAILABLE', '已取消任务没有可用报告');
    }
    const report = cloneFixture(runReportFixture);
    report.run_id = runId;
    report.status = detail.status;
    report.verdict = detail.verdict;
    report.error = detail.error;
    report.artifacts = report.artifacts.map((artifact) => ({
      ...artifact,
      run_id: runId,
    }));
    return HttpResponse.json(report);
  }),

  http.post('/api/v1/test-runs/:runId/cancel', ({ params }) => {
    const runId = String(params.runId);
    const detail = details.get(runId);
    if (!detail) return error(404, 'RUN_NOT_FOUND', '测试任务不存在');
    if (['succeeded', 'errored', 'cancelled'].includes(detail.status)) {
      return error(409, 'RUN_NOT_CANCELLABLE', '当前任务不可取消');
    }
    const queued = detail.status === 'queued';
    detail.cancellation_requested = true;
    if (queued) {
      detail.status = 'cancelled';
      detail.finished_at = new Date().toISOString();
    }
    return HttpResponse.json(
      {
        run_id: runId,
        status: detail.status,
        cancellation_requested: true,
      },
      { status: queued ? 200 : 202 },
    );
  }),

  http.get('/api/v1/artifacts/:artifactId', ({ params }) => {
    const artifactId = String(params.artifactId);
    if (artifactId.includes('expired'))
      return error(410, 'ARTIFACT_EXPIRED', '证据已超过保留期限');
    if (artifactId.includes('unavailable'))
      return error(503, 'ARTIFACT_UNAVAILABLE', '证据存储暂不可用');
    if (artifactId.includes('missing'))
      return error(404, 'ARTIFACT_NOT_FOUND', '证据不存在');
    if (artifactId.includes('trace')) {
      return new HttpResponse(new Uint8Array([80, 75, 3, 4]), {
        headers: {
          'Content-Type': 'application/zip',
          'Content-Disposition': `attachment; filename="${artifactId}.zip"`,
          'Cache-Control': 'private, no-store',
        },
      });
    }
    return HttpResponse.json(
      { artifact_id: artifactId, source: 'contract-mock', redacted: true },
      { headers: { 'Cache-Control': 'private, no-store' } },
    );
  }),
];

export { createRunFixture };
