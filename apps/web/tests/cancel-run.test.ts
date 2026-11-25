import { flushPromises, mount } from '@vue/test-utils';
import { delay, http, HttpResponse } from 'msw';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as api from '../src/api';
import type { CancelRunResponse, PublishedEvent, RunDetail } from '../src/api';
import RunDetailView from '../src/features/test-runs/RunDetailView.vue';
import { cloneFixture, runDetailFixture } from './fixtures/api';
import { server } from './fixtures/server';

async function mountRun() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/runs', component: { template: '<p>list</p>' } },
      { path: '/runs/:runId', component: RunDetailView },
    ],
  });
  await router.push('/runs/run_cancel');
  await router.isReady();
  return {
    wrapper: mount(RunDetailView, { global: { plugins: [router] } }),
    router,
  };
}

function queuedRun(): RunDetail {
  return {
    ...cloneFixture(runDetailFixture),
    run_id: 'run_cancel',
    status: 'queued',
    verdict: null,
    summary: null,
    progress: { total_cases: null, completed_cases: 0 },
    started_at: null,
    finished_at: null,
  };
}

function pendingCancel() {
  let finish!: (result: CancelRunResponse) => void;
  const response = new Promise<CancelRunResponse>((resolve) => {
    finish = resolve;
  });
  return { response, finish };
}

function unavailableReport() {
  return http.get('/api/v1/test-runs/:runId/report', () =>
    HttpResponse.json(
      {
        error: {
          code: 'REPORT_UNAVAILABLE',
          message: '已取消任务没有可用报告',
          request_id: 'req_cancelled_report',
        },
      },
      { status: 409 },
    ),
  );
}

describe('F05 cancellation', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('applies queued cancellation and ignores duplicate clicks', async () => {
    let calls = 0;
    const current = queuedRun();
    server.use(
      http.get('/api/v1/test-runs/:runId', () => HttpResponse.json(current)),
      unavailableReport(),
      http.post('/api/v1/test-runs/:runId/cancel', async () => {
        calls += 1;
        await delay(50);
        current.status = 'cancelled';
        current.cancellation_requested = true;
        return HttpResponse.json({
          run_id: current.run_id,
          status: 'cancelled',
          cancellation_requested: true,
        });
      }),
    );
    const { wrapper } = await mountRun();
    await vi.waitFor(() => expect(wrapper.text()).toContain('取消运行'));
    const button = wrapper.get('button.button-hero');
    await button.trigger('click');
    await button.trigger('click');
    await vi.waitFor(() => expect(wrapper.text()).toContain('已取消'));
    expect(calls).toBe(1);
  });

  it('keeps the terminal detail when the pending cancellation response arrives', async () => {
    const stream = new EventTarget();
    vi.stubGlobal(
      'EventSource',
      class {
        addEventListener = stream.addEventListener.bind(stream);
        close = vi.fn();
      },
    );
    const current = queuedRun();
    server.use(
      http.get('/api/v1/test-runs/:runId', () => HttpResponse.json(current)),
      unavailableReport(),
    );
    const pending = pendingCancel();
    const cancel = vi
      .spyOn(api, 'cancelRun')
      .mockReturnValueOnce(pending.response);
    const { wrapper } = await mountRun();
    await vi.waitFor(() => expect(wrapper.text()).toContain('取消运行'));
    const publish = (type: string, sequence: number, payload = {}) => {
      const event: PublishedEvent = {
        schema_version: 1,
        event_id: `evt_${sequence}`,
        sequence,
        run_id: current.run_id,
        type,
        timestamp: current.created_at,
        case_id: null,
        step_id: null,
        payload,
      };
      stream.dispatchEvent(
        new MessageEvent(type, { data: JSON.stringify(event) }),
      );
    };
    publish('run.started', 1);
    await wrapper.get('button.button-hero').trigger('click');
    current.status = 'cancelled';
    current.cancellation_requested = true;
    publish('run.cancelled', 2, {
      status: 'cancelled',
      verdict: null,
      error: null,
    });
    await vi.waitFor(() => expect(wrapper.text()).toContain('已取消'));
    expect(cancel.mock.calls[0]?.[1]?.aborted).toBe(true);

    pending.finish({
      run_id: current.run_id,
      status: 'running',
      cancellation_requested: true,
    });
    await flushPromises();
    expect(wrapper.text()).toContain('已取消');
    expect(wrapper.text()).not.toContain('正在等待 Worker');
    expect(wrapper.find('button.button-hero').exists()).toBe(false);
    wrapper.unmount();
  });

  it('ignores a previous Run response while the next Run is being cancelled', async () => {
    server.use(
      http.get('/api/v1/test-runs/:runId', ({ params }) =>
        HttpResponse.json({
          ...queuedRun(),
          run_id: String(params.runId),
          goal: String(params.runId),
        }),
      ),
    );
    const previous = pendingCancel();
    const next = pendingCancel();
    const cancel = vi
      .spyOn(api, 'cancelRun')
      .mockReturnValueOnce(previous.response)
      .mockReturnValueOnce(next.response);
    const { wrapper, router } = await mountRun();
    await vi.waitFor(() => expect(wrapper.text()).toContain('取消运行'));
    await wrapper.get('button.button-hero').trigger('click');
    await router.push('/runs/run_next');
    await vi.waitFor(() => expect(wrapper.get('h1').text()).toBe('run_next'));
    expect(cancel.mock.calls[0]?.[1]?.aborted).toBe(true);
    await wrapper.get('button.button-hero').trigger('click');
    expect(wrapper.get('button.button-hero').text()).toBe('正在取消…');

    previous.finish({
      run_id: 'run_cancel',
      status: 'cancelled',
      cancellation_requested: true,
    });
    await flushPromises();
    expect(wrapper.get('button.button-hero').text()).toBe('正在取消…');
    next.finish({
      run_id: 'run_next',
      status: 'running',
      cancellation_requested: true,
    });
    await vi.waitFor(() =>
      expect(wrapper.get('button.button-hero').text()).toBe('取消已请求'),
    );
    wrapper.unmount();
  });
});
