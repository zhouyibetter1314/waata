import { mount } from '@vue/test-utils';
import { createPinia } from 'pinia';
import { http, HttpResponse } from 'msw';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';
import type { CreateRunRequest } from '../src/api';
import ScenarioWorkspaceView from '../src/features/catalog/ScenarioWorkspaceView.vue';
import type {
  CatalogApplication,
  CatalogScenario,
} from '../src/features/catalog/store';
import { runCreatedFixture } from './fixtures/api';
import { server } from './fixtures/server';

const storageKey = 'waata.frontend.catalog.v1';
const retiredApplication: CatalogApplication = {
  id: 'app_4gaboards',
  name: '4gaBoards',
  base_url: 'http://localhost:3000/',
  credential_ref: 'boards_local_fixture',
  version: '3.2.16',
};
const savedApplication: CatalogApplication = {
  ...retiredApplication,
  base_url: 'http://127.0.0.1:3000/',
  credential_ref: null,
};
const retiredScenario: CatalogScenario = {
  id: 'scenario_create_project',
  application_id: retiredApplication.id,
  name: '创建项目并验证两个位置',
  goal: '在本地 4gaBoards 创建名为 Course Test 01 的项目。',
  expected_behavior: '创建完成后，仪表盘和侧边栏均显示 Course Test 01。',
  source: 'C1 正式样例',
};
const savedScenario: CatalogScenario = {
  ...retiredScenario,
  id: 'scenario_login_form',
  name: '查看登录表单',
  goal: '打开 4gaBoards 首页并查看登录表单。',
  expected_behavior: '账号框和密码框可见。',
  source: '自建场景',
};

function saveCatalog(
  scenarios: CatalogScenario[],
  application = savedApplication,
): void {
  localStorage.setItem(
    storageKey,
    JSON.stringify({
      applications: [application],
      scenarios,
      maxSteps: 12,
    }),
  );
}

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
  it('removes an unmodified sample application and scenario', async () => {
    saveCatalog([retiredScenario], retiredApplication);
    const { wrapper } = await mountView();
    expect(wrapper.text()).toContain('请先添加被测应用');
    expect(JSON.parse(localStorage.getItem(storageKey)!)).toMatchObject({
      applications: [],
      scenarios: [],
    });
  });

  it('keeps the former sample application when a saved scenario uses it', async () => {
    saveCatalog([retiredScenario, savedScenario], retiredApplication);
    const { wrapper } = await mountView();
    expect(wrapper.text()).not.toContain(retiredScenario.name);
    expect(wrapper.text()).toContain(savedScenario.name);
    expect(JSON.parse(localStorage.getItem(storageKey)!)).toMatchObject({
      applications: [retiredApplication],
      scenarios: [savedScenario],
    });
  });

  it('keeps user edits to the former sample', async () => {
    const editedScenario = { ...retiredScenario, goal: savedScenario.goal };
    saveCatalog([editedScenario]);
    const { wrapper } = await mountView();
    expect(wrapper.text()).toContain(editedScenario.goal);
    expect(JSON.parse(localStorage.getItem(storageKey)!).scenarios).toEqual([
      editedScenario,
    ]);
  });

  it('converts a saved scenario to a C1 create request', async () => {
    saveCatalog([savedScenario]);
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
      target_url: 'http://127.0.0.1:3000/',
      goal: savedScenario.goal,
      expected_behavior: savedScenario.expected_behavior,
      credential_ref: null,
      options: { max_steps_per_case: 12 },
    });
  });

  it('deletes a local scenario without inventing a Run DELETE endpoint', async () => {
    saveCatalog([savedScenario]);
    const { wrapper } = await mountView();
    await wrapper.get('.catalog-actions .text-danger').trigger('click');
    expect(wrapper.text()).toContain('还没有场景');
  });
});
