import { expect, test } from '@playwright/test';

test('replays C4 events and reviews the C1 report with C5 evidence', async ({
  page,
}) => {
  await page.goto('/runs/run_4gaboards_001');

  await expect(page.getByRole('heading', { name: '执行时间线' })).toBeVisible();
  await expect(page.getByText('任务开始运行')).toBeVisible();
  await expect(page.getByText('任务正常完成')).toBeVisible();
  await expect(page.getByText('C4 · #21')).toBeVisible();

  await expect(page.getByRole('heading', { name: '报告与证据' })).toBeVisible();
  await expect(page.getByText('断言复核（2）')).toBeVisible();
  await expect(
    page.getByText('art_4ga_dashboard', { exact: true }),
  ).toBeVisible();

  await page
    .getByRole('button', { name: '查看证据 art_4ga_dashboard' })
    .click();
  await expect(page.getByText('"redacted": true')).toBeVisible();

  await page.getByRole('link', { name: '场景与应用' }).click();
  await expect(page).toHaveURL(/\/scenarios$/);
  await expect(page.getByRole('heading', { name: '场景与应用' })).toBeVisible();
  await expect(page.getByText('创建项目并验证两个位置')).toBeVisible();
});
