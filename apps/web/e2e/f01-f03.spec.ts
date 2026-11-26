import { expect, test } from '@playwright/test';
import type { RunDetail } from '../src/api';
import { runCreatedFixture, toRunSummary } from '../tests/fixtures/api';

test('validates, submits, lists and opens a queued test run', async ({
  page,
}) => {
  const created = { ...runCreatedFixture, run_id: 'run_ui_01' };
  const input = {
    target_url: 'http://localhost:3000/',
    goal: '在本地 4gaBoards 创建 Course Test 01',
    expected_behavior: '仪表盘和侧边栏均显示 Course Test 01',
    credential_ref: 'boards_local_fixture',
  };
  const detail: RunDetail = {
    ...created,
    target_url: input.target_url,
    goal: input.goal,
    expected_behavior: input.expected_behavior,
    started_at: null,
    finished_at: null,
    verdict: null,
    progress: { total_cases: null, completed_cases: 0 },
    summary: null,
    error: null,
    cancellation_requested: false,
  };
  await page.route('**/api/v1/test-runs', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toMatchObject(input);
    await route.fulfill({ status: 202, json: created });
  });
  await page.route('**/api/v1/test-runs?*', (route) =>
    route.fulfill({
      json: { items: [toRunSummary(detail)], page: 1, page_size: 20, total: 1 },
    }),
  );
  await page.route(`**/api/v1/test-runs/${created.run_id}`, (route) =>
    route.fulfill({ json: detail }),
  );
  await page.route(
    (url) => url.pathname === `/api/v1/test-runs/${created.run_id}/events`,
    (route) =>
      route.fulfill({
        contentType: 'text/event-stream',
        body: ': keep-alive\n\n',
      }),
  );

  await page.goto('/runs/new');
  await expect(page.getByLabel('目标地址')).toHaveValue('');

  await page
    .getByLabel('目标地址')
    .fill('http://user:password@localhost:3000/');
  await page.getByRole('button', { name: '提交任务' }).click();
  await expect(page.getByText('目标地址不能包含用户名或密码')).toBeVisible();
  await expect(page.getByText('请输入自然语言测试目标')).toBeVisible();
  await expect(page.getByText('请输入预期行为')).toBeVisible();

  await page.getByLabel('目标地址').fill(input.target_url);
  await page.getByLabel('自然语言测试目标').fill(input.goal);
  await page.getByLabel('预期行为').fill(input.expected_behavior);
  await page.getByLabel('凭据引用（可选）').fill(input.credential_ref);
  await page.getByRole('button', { name: '提交任务' }).click();

  await expect(page).toHaveURL(`/runs/${created.run_id}`);
  await expect(page.getByText('排队中', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('未产生', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('0 / 待规划', { exact: true })).toBeVisible();

  await page.getByRole('link', { name: '测试任务' }).click();
  await page.getByRole('link', { name: input.goal }).click();
  await expect(page).toHaveURL(`/runs/${created.run_id}`);
});
