import { expect, test } from '@playwright/test';

test('validates, submits, lists and opens a Mock test run', async ({
  page,
}) => {
  await page.goto('/runs/new');

  await page
    .getByLabel('目标地址')
    .fill('http://user:password@localhost:3000/');
  await page.getByRole('button', { name: '提交任务' }).click();
  await expect(page.getByText('目标地址不能包含用户名或密码')).toBeVisible();
  await expect(page.getByText('请输入自然语言测试目标')).toBeVisible();
  await expect(page.getByText('请输入预期行为')).toBeVisible();

  await page.getByLabel('目标地址').fill('http://localhost:3000/');
  await page
    .getByLabel('自然语言测试目标')
    .fill('在本地 4gaBoards 创建 Course Test 01');
  await page.getByLabel('预期行为').fill('仪表盘和侧边栏均显示 Course Test 01');
  await page.getByLabel('凭据引用（可选）').fill('boards_local_fixture');
  await page.getByRole('button', { name: '提交任务' }).click();

  await expect(page).toHaveURL(/\/runs\/run_4gaboards_002$/);
  await expect(page.getByText('排队中', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('未产生', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('0 / 待规划', { exact: true })).toBeVisible();

  await page.getByRole('link', { name: '测试任务' }).click();
  await expect(
    page.getByText('在本地 4gaBoards 创建 Course Test 01'),
  ).toBeVisible();
  await page.getByText('在本地 4gaBoards 创建 Course Test 01').click();
  await expect(page).toHaveURL(/\/runs\/run_4gaboards_002$/);
});
