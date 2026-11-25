import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import type { RunDetail } from '../src/api';
import { runDetailFixture, runReportFixture } from '../tests/fixtures/api';

test('updates progress via C4, recovers a missing event and displays C5 evidence', async ({
  page,
}) => {
  const eventStream = await readFile(
    new URL(
      '../../../contracts/events/examples/4gaboards-events.sse',
      import.meta.url,
    ),
    'utf8',
  );
  const detailPath = `/api/v1/test-runs/${runDetailFixture.run_id}`;
  const evidenceId = 'art_4ga_dashboard';
  const assertionCount = runReportFixture.cases.reduce(
    (total, testCase) => total + testCase.assertions.length,
    0,
  );
  const sequences = [...eventStream.matchAll(/^id: (\d+)$/gm)].map(
    (match) => match[1],
  );
  const terminalSequence = sequences.at(-1);
  const chunks = eventStream.trim().split('\n\n');
  const reportIndex = chunks.findIndex((chunk) =>
    chunk.includes('event: report.generated'),
  );
  expect(reportIndex).toBeGreaterThan(0);
  const lastProgressSequence = sequences[reportIndex - 1];
  const queued: RunDetail = {
    ...runDetailFixture,
    status: 'queued',
    verdict: null,
    started_at: null,
    finished_at: null,
    progress: { total_cases: null, completed_cases: 0 },
    summary: null,
  };
  let terminalPublished = false;
  let publishTerminal!: () => void;
  const terminalReady = new Promise<void>((resolve) => {
    publishTerminal = resolve;
  });

  await page.route(`**${detailPath}`, (route) =>
    route.fulfill({ json: terminalPublished ? runDetailFixture : queued }),
  );
  await page.route(
    (url) => url.pathname === `${detailPath}/events`,
    async (route) => {
      const cursor = new URL(route.request().url()).searchParams.get('after');
      if (cursor === '0') {
        const partial = [...chunks.slice(0, reportIndex), chunks.at(-1)];
        await route.fulfill({
          contentType: 'text/event-stream',
          body: `${partial.join('\n\n')}\n\n`,
        });
        return;
      }
      expect(cursor).toBe(lastProgressSequence);
      await terminalReady;
      terminalPublished = true;
      await route.fulfill({
        contentType: 'text/event-stream',
        body: `${chunks.slice(reportIndex).join('\n\n')}\n\n`,
      });
    },
  );
  await page.route(`**${detailPath}/report`, (route) =>
    route.fulfill({ json: runReportFixture }),
  );
  await page.route(`**/api/v1/artifacts/${evidenceId}`, (route) =>
    route.fulfill({ json: { artifact_id: evidenceId, redacted: true } }),
  );

  try {
    await page.goto(`/runs/${runDetailFixture.run_id}`);
    await expect(
      page.getByRole('heading', { name: '执行时间线' }),
    ).toBeVisible();
    await expect(page.getByText('任务开始运行')).toBeVisible();
    await expect(
      page.getByText('运行中', { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: '本机浏览器画面' }),
    ).toHaveCount(0);
    await expect(
      page.getByText(
        `${runDetailFixture.progress.completed_cases} / ${runDetailFixture.progress.total_cases}`,
        { exact: true },
      ),
    ).toBeVisible();
  } finally {
    publishTerminal();
  }
  await expect(page.getByText('任务正常完成')).toBeVisible();
  await expect(page.getByText(`C4 · #${terminalSequence}`)).toBeVisible();
  await expect(page.getByText('10.70 秒', { exact: true })).toBeVisible();

  await expect(page.getByRole('heading', { name: '报告与证据' })).toBeVisible();
  await expect(page.getByText(`断言复核（${assertionCount}）`)).toBeVisible();
  await expect(page.getByText(evidenceId, { exact: true })).toBeVisible();

  await page.getByRole('button', { name: `查看证据 ${evidenceId}` }).click();
  await expect(page.getByText('"redacted": true')).toBeVisible();

  await page.getByRole('link', { name: '场景与应用' }).click();
  await expect(page).toHaveURL(/\/scenarios$/);
  await expect(page.getByRole('heading', { name: '场景与应用' })).toBeVisible();
  await expect(
    page.getByText('请先添加被测应用，再创建测试场景。'),
  ).toBeVisible();
  await expect(page.getByText('还没有场景', { exact: false })).toBeVisible();
});
