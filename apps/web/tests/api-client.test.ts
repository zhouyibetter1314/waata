import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import {
  ApiError,
  artifactUrl,
  cancelRun,
  createRun,
  getArtifact,
  getRun,
  getRunReport,
  listRuns,
  runEventsUrl,
  type CreateRunRequest,
} from '../src/api';
import { createRunFixture, runCreatedFixture } from './fixtures/api';
import { server } from './fixtures/server';

describe('C1 API client', () => {
  it('submits the create payload with POST', async () => {
    let method = '';
    let body: unknown;
    server.use(
      http.post('/api/v1/test-runs', async ({ request }) => {
        method = request.method;
        body = await request.json();
        return HttpResponse.json(runCreatedFixture, { status: 202 });
      }),
    );
    await createRun(createRunFixture);
    expect(method).toBe('POST');
    expect(body).toEqual(createRunFixture);
  });

  it('sends C1 pagination parameters', async () => {
    let query = '';
    server.use(
      http.get('/api/v1/test-runs', ({ request }) => {
        query = new URL(request.url).search;
        return HttpResponse.json({
          items: [],
          page: 3,
          page_size: 7,
          total: 0,
        });
      }),
    );
    await listRuns({ page: 3, pageSize: 7 });
    expect(new URLSearchParams(query).get('page')).toBe('3');
    expect(new URLSearchParams(query).get('page_size')).toBe('7');
  });

  it('encodes opaque Run IDs for detail, report and event paths', async () => {
    const runId = 'run /?#测试';
    const paths: string[] = [];
    server.use(
      http.get(/\/api\/v1\/test-runs\/.+/, ({ request }) => {
        paths.push(new URL(request.url).pathname);
        return HttpResponse.json({});
      }),
    );
    await getRun(runId);
    await getRunReport(runId);
    expect(paths).toEqual([
      `/api/v1/test-runs/${encodeURIComponent(runId)}`,
      `/api/v1/test-runs/${encodeURIComponent(runId)}/report`,
    ]);
    expect(runEventsUrl(runId, 17)).toBe(
      `/api/v1/test-runs/${encodeURIComponent(runId)}/events?after=17`,
    );
  });

  it('posts cancellation without a request body', async () => {
    let body = 'not inspected';
    server.use(
      http.post(
        '/api/v1/test-runs/:runId/cancel',
        async ({ request, params }) => {
          body = await request.text();
          return HttpResponse.json({
            run_id: String(params.runId),
            status: 'running',
            cancellation_requested: true,
          });
        },
      ),
    );
    await cancelRun('run_cancel');
    expect(body).toBe('');
  });

  it('encodes artifact IDs for URL construction and reads', async () => {
    const artifactId = 'artifact /?#截图';
    let path = '';
    server.use(
      http.get(/\/api\/v1\/artifacts\/.+/, ({ request }) => {
        path = new URL(request.url).pathname;
        return HttpResponse.json({ ok: true });
      }),
    );
    const response = await getArtifact(artifactId);
    expect(response.ok).toBe(true);
    expect(path).toBe(`/api/v1/artifacts/${encodeURIComponent(artifactId)}`);
    expect(artifactUrl(artifactId)).toBe(
      `/api/v1/artifacts/${encodeURIComponent(artifactId)}`,
    );
  });

  it.each([
    [403, 'TARGET_NOT_ALLOWED'],
    [422, 'VALIDATION_ERROR'],
    [503, 'SERVICE_UNAVAILABLE'],
  ])(
    'preserves error code and request_id for HTTP %s',
    async (status, code) => {
      server.use(
        http.post('/api/v1/test-runs', () =>
          HttpResponse.json(
            {
              error: {
                code,
                message: '契约错误',
                request_id: 'req_contract_001',
              },
            },
            { status },
          ),
        ),
      );
      let caught: unknown;
      try {
        await createRun(createRunFixture as CreateRunRequest);
      } catch (error) {
        caught = error;
      }
      expect(caught).toBeInstanceOf(ApiError);
      expect(caught).toMatchObject({
        status,
        code,
        requestId: 'req_contract_001',
      });
    },
  );
});
