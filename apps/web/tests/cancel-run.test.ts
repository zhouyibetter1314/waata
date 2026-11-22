import { mount } from '@vue/test-utils';
import { delay, http, HttpResponse } from 'msw';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';
import type { RunDetail } from '../src/api';
import RunDetailView from '../src/features/test-runs/RunDetailView.vue';
import { cloneFixture, runDetailFixture } from '../src/mocks/fixtures';
import { server } from '../src/mocks/server';

async function mountQueued() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/runs', component: { template: '<p>list</p>' } },
      { path: '/runs/:runId', component: RunDetailView },
    ],
  });
  await router.push('/runs/run_cancel');
  await router.isReady();
  return mount(RunDetailView, { global: { plugins: [router] } });
}

describe('F05 cancellation', () => {
  it('applies queued cancellation and ignores duplicate clicks', async () => {
    let calls = 0;
    const current: RunDetail = {
      ...cloneFixture(runDetailFixture),
      run_id: 'run_cancel',
      status: 'queued',
      verdict: null,
      summary: null,
      progress: { total_cases: null, completed_cases: 0 },
      started_at: null,
      finished_at: null,
    };
    server.use(
      http.get('/api/v1/test-runs/:runId', () => HttpResponse.json(current)),
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
    const wrapper = await mountQueued();
    await vi.waitFor(() => expect(wrapper.text()).toContain('取消运行'));
    const button = wrapper.get('button.button-hero');
    await button.trigger('click');
    await button.trigger('click');
    await vi.waitFor(() => expect(wrapper.text()).toContain('已取消'));
    expect(calls).toBe(1);
  });
});
