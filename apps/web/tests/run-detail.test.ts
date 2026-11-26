import { mount } from '@vue/test-utils';
import { delay, http, HttpResponse } from 'msw';
import { createMemoryHistory, createRouter, type Router } from 'vue-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import RunDetailView from '../src/features/test-runs/RunDetailView.vue';
import {
  cloneFixture,
  runDetailFixture,
  runReportFixture,
} from './fixtures/api';
import { server } from './fixtures/server';
import type { RunDetail } from '../src/api';

async function mountView(runId = 'run_4gaboards_001') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/runs', component: { template: '<p>list</p>' } },
      { path: '/runs/:runId', name: 'run-detail', component: RunDetailView },
    ],
  });
  await router.push(`/runs/${encodeURIComponent(runId)}`);
  await router.isReady();
  const wrapper = mount(RunDetailView, { global: { plugins: [router] } });
  return { wrapper, router };
}

function detail(overrides: Partial<RunDetail>): RunDetail {
  return { ...cloneFixture(runDetailFixture), ...overrides };
}

describe('F03 run detail', () => {
  beforeEach(() => {
    server.use(
      http.get('/api/v1/test-runs/:runId/report', () =>
        HttpResponse.json(runReportFixture),
      ),
    );
  });

  it('renders succeeded + failed and preserves zero summary values', async () => {
    server.use(
      http.get('/api/v1/test-runs/:runId', () =>
        HttpResponse.json(
          detail({
            verdict: 'failed',
            progress: { total_cases: 2, completed_cases: 2 },
            summary: { passed: 1, failed: 1, blocked: 0, inconclusive: 0 },
          }),
        ),
      ),
    );
    const { wrapper } = await mountView();
    await vi.waitFor(() => expect(wrapper.text()).toContain('发现失败'));
    expect(wrapper.text()).toContain('正常完成');
    expect(wrapper.text()).toContain('用例汇总');
    expect(wrapper.text()).toContain('无法判定');

    const taskInfo = wrapper.get('[aria-labelledby="run-request-title"]');
    expect(taskInfo.get('dt:nth-of-type(1)').text()).toBe('自然语言测试目标');
    expect(taskInfo.get('dd:nth-of-type(1)').text()).toBe(
      runDetailFixture.goal,
    );
    expect(taskInfo.get('dt:nth-of-type(2)').text()).toBe('预期行为');
    expect(taskInfo.get('dd:nth-of-type(2)').text()).toBe(
      runDetailFixture.expected_behavior,
    );
  });

  it('keeps the verdict and report without repeating a single case as a summary', async () => {
    server.use(
      http.get('/api/v1/test-runs/:runId', () =>
        HttpResponse.json(runDetailFixture),
      ),
    );
    const { wrapper } = await mountView();
    await vi.waitFor(() => expect(wrapper.text()).toContain('断言复核'));
    expect(wrapper.text()).toContain('通过');
    expect(wrapper.text()).not.toContain('用例汇总');
  });

  it.each([
    [
      'errored + null',
      detail({
        status: 'errored',
        verdict: null,
        summary: null,
        error: { code: 'MODEL_UNAVAILABLE', message: '模型服务不可用' },
      }),
      '模型服务不可用',
    ],
    [
      'cancelled',
      detail({
        status: 'cancelled',
        verdict: null,
        summary: null,
        error: null,
      }),
      '已取消',
    ],
    [
      'not started',
      detail({
        status: 'queued',
        verdict: null,
        summary: null,
        error: null,
        progress: { total_cases: null, completed_cases: 0 },
        started_at: null,
        finished_at: null,
      }),
      '待规划',
    ],
  ])('renders %s details', async (_name, response, expected) => {
    server.use(
      http.get('/api/v1/test-runs/:runId', () => HttpResponse.json(response)),
    );
    const { wrapper } = await mountView();
    await vi.waitFor(() => expect(wrapper.text()).toContain(expected));
    expect(wrapper.text()).toContain('未产生');
  });

  it('shows detail API errors with request_id', async () => {
    server.use(
      http.get('/api/v1/test-runs/:runId', () =>
        HttpResponse.json(
          {
            error: {
              code: 'RUN_NOT_FOUND',
              message: '测试任务不存在',
              request_id: 'req_detail',
            },
          },
          { status: 404 },
        ),
      ),
    );
    const { wrapper } = await mountView('missing');
    await vi.waitFor(() => expect(wrapper.text()).toContain('测试任务不存在'));
    expect(wrapper.text()).toContain('req_detail');
  });

  it('does not let a delayed old Run overwrite the current route', async () => {
    server.use(
      http.get('/api/v1/test-runs/:runId', async ({ params }) => {
        const runId = String(params.runId);
        await delay(runId === 'run_old' ? 120 : 10);
        return HttpResponse.json(
          detail({ run_id: runId, goal: `目标 ${runId}` }),
        );
      }),
    );
    const { wrapper, router } = await mountView('run_old');
    await (router as Router).push('/runs/run_new');
    await vi.waitFor(() => expect(wrapper.text()).toContain('目标 run_new'));
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(wrapper.text()).not.toContain('目标 run_old');
  });
});
