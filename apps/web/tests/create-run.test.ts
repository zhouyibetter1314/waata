import { flushPromises, mount } from '@vue/test-utils';
import { delay, http, HttpResponse } from 'msw';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';
import CreateRunView from '../src/features/test-runs/CreateRunView.vue';
import { runCreatedFixture } from '../src/mocks/fixtures';
import { server } from '../src/mocks/server';

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/runs/new', component: CreateRunView },
      {
        path: '/runs/:runId',
        name: 'run-detail',
        component: { template: '<p>detail</p>' },
      },
      { path: '/runs', component: { template: '<p>list</p>' } },
    ],
  });
  await router.push('/runs/new');
  await router.isReady();
  return {
    wrapper: mount(CreateRunView, { global: { plugins: [router] } }),
    router,
  };
}

async function fillRequired(wrapper: ReturnType<typeof mount>) {
  await wrapper.find('[name="goal"]').setValue('创建 Course Test 01');
  await wrapper
    .find('[name="expected_behavior"]')
    .setValue('仪表盘和侧边栏均显示项目');
}

describe('F02 create run', () => {
  it('validates empty goal, empty expected behavior and URL userinfo', async () => {
    const { wrapper } = await mountView();
    await wrapper
      .find('[name="target_url"]')
      .setValue('http://user:password@localhost:3000/');
    await wrapper.find('form').trigger('submit');
    expect(wrapper.text()).toContain('目标地址不能包含用户名或密码');
    expect(wrapper.text()).toContain('请输入自然语言测试目标');
    expect(wrapper.text()).toContain('请输入预期行为');
  });

  it('redirects to the opaque run_id after a Mock 202 response', async () => {
    const { wrapper, router } = await mountView();
    await fillRequired(wrapper);
    await wrapper.find('form').trigger('submit');
    await vi.waitFor(() =>
      expect(router.currentRoute.value.params.runId).toBe('run_4gaboards_002'),
    );
  });

  it.each([
    [403, 'TARGET_NOT_ALLOWED'],
    [422, 'VALIDATION_ERROR'],
    [503, 'SERVICE_UNAVAILABLE'],
  ])('shows HTTP %s and preserves input', async (status, code) => {
    server.use(
      http.post('/api/v1/test-runs', () =>
        HttpResponse.json(
          {
            error: {
              code,
              message: `错误 ${code}`,
              request_id: `req_${status}`,
            },
          },
          { status },
        ),
      ),
    );
    const { wrapper } = await mountView();
    await fillRequired(wrapper);
    await wrapper.find('form').trigger('submit');
    await vi.waitFor(() => expect(wrapper.text()).toContain(`错误 ${code}`));
    expect(wrapper.text()).toContain(`req_${status}`);
    expect(
      (wrapper.find('[name="goal"]').element as HTMLTextAreaElement).value,
    ).toBe('创建 Course Test 01');
  });

  it('sends only one request while submission is pending', async () => {
    let calls = 0;
    server.use(
      http.post('/api/v1/test-runs', async () => {
        calls += 1;
        await delay(100);
        return HttpResponse.json(runCreatedFixture, { status: 202 });
      }),
    );
    const { wrapper } = await mountView();
    await fillRequired(wrapper);
    const form = wrapper.find('form');
    await form.trigger('submit');
    await form.trigger('submit');
    await flushPromises();
    expect(calls).toBe(1);
    expect(
      wrapper.get('button[type="submit"]').attributes('disabled'),
    ).toBeDefined();
  });
});
