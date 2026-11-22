import { flushPromises, mount } from '@vue/test-utils';
import { createPinia } from 'pinia';
import { http, HttpResponse } from 'msw';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';
import RunListView from '../src/features/test-runs/RunListView.vue';
import { runDetailFixture, toRunSummary } from '../src/mocks/fixtures';
import { server } from '../src/mocks/server';

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/runs', component: RunListView },
      { path: '/runs/new', component: { template: '<p>new</p>' } },
      { path: '/runs/:runId', component: { template: '<p>detail</p>' } },
    ],
  });
  await router.push('/runs');
  await router.isReady();
  return mount(RunListView, { global: { plugins: [createPinia(), router] } });
}

describe('F03 run list', () => {
  it('renders pagination values and a succeeded + failed summary', async () => {
    server.use(
      http.get('/api/v1/test-runs', ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get('page')).toBe('1');
        expect(url.searchParams.get('page_size')).toBe('20');
        return HttpResponse.json({
          items: [{ ...toRunSummary(runDetailFixture), verdict: 'failed' }],
          page: 1,
          page_size: 20,
          total: 21,
        });
      }),
    );
    const wrapper = await mountView();
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain(runDetailFixture.goal),
    );
    expect(wrapper.text()).toContain('正常完成');
    expect(wrapper.text()).toContain('发现失败');
    expect(wrapper.text()).toContain('第 1 / 2 页');
  });

  it('renders the empty state', async () => {
    server.use(
      http.get('/api/v1/test-runs', () =>
        HttpResponse.json({ items: [], page: 1, page_size: 20, total: 0 }),
      ),
    );
    const wrapper = await mountView();
    await vi.waitFor(() => expect(wrapper.text()).toContain('还没有测试任务'));
  });

  it('renders an API failure and allows retry', async () => {
    server.use(
      http.get('/api/v1/test-runs', () =>
        HttpResponse.json(
          {
            error: {
              code: 'SERVICE_UNAVAILABLE',
              message: '列表服务不可用',
              request_id: 'req_list',
            },
          },
          { status: 503 },
        ),
      ),
    );
    const wrapper = await mountView();
    await flushPromises();
    await vi.waitFor(() => expect(wrapper.text()).toContain('列表服务不可用'));
    expect(wrapper.text()).toContain('重试');
  });
});
