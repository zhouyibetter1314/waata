import { mount } from '@vue/test-utils';
import { createPinia } from 'pinia';
import { http, HttpResponse } from 'msw';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';
import type { CreateRunRequest } from '../src/api';
import ScenarioWorkspaceView from '../src/features/catalog/ScenarioWorkspaceView.vue';
import { runCreatedFixture } from '../src/mocks/fixtures';
import { server } from '../src/mocks/server';

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/scenarios', component: ScenarioWorkspaceView },
      { path: '/runs', component: { template: '<p>runs</p>' } },
      { path: '/runs/:runId', component: { template: '<p>detail</p>' } },
    ],
  });
  await router.push('/scenarios');
  await router.isReady();
  return {
    wrapper: mount(ScenarioWorkspaceView, {
      global: { plugins: [createPinia(), router] },
    }),
    router,
  };
}

describe('contract-driven local scenario catalog', () => {
  it('converts a saved scenario to a C1 create request', async () => {
    let requestBody: CreateRunRequest | null = null;
    server.use(
      http.post('/api/v1/test-runs', async ({ request }) => {
        requestBody = (await request.json()) as CreateRunRequest;
        return HttpResponse.json(runCreatedFixture, { status: 202 });
      }),
    );
    const { wrapper, router } = await mountView();
    const runButton = wrapper
      .findAll('button')
      .find((button) => button.text() === '运行');
    expect(runButton).toBeDefined();
    await runButton!.trigger('click');
    await vi.waitFor(() =>
      expect(router.currentRoute.value.path).toContain('/runs/'),
    );
    expect(requestBody).toMatchObject({
      target_url: 'http://localhost:3000/',
      goal: '在本地 4gaBoards 创建名为 Course Test 01 的项目。',
      expected_behavior: '创建完成后，仪表盘和侧边栏均显示 Course Test 01。',
      credential_ref: 'boards_local_fixture',
      options: { max_steps_per_case: 12 },
    });
  });

  it('deletes a local scenario without inventing a Run DELETE endpoint', async () => {
    const { wrapper } = await mountView();
    const deleteButton = wrapper
      .findAll('button')
      .find((button) => button.text() === '删除');
    expect(deleteButton).toBeDefined();
    await deleteButton!.trigger('click');
    expect(wrapper.text()).toContain('还没有场景');
  });
});
