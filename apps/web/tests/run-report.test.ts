import { mount } from '@vue/test-utils';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import RunReportPanel from '../src/features/test-runs/RunReportPanel.vue';
import { cloneFixture, runReportFixture } from '../src/mocks/fixtures';
import { server } from '../src/mocks/server';

describe('F06 report and evidence', () => {
  it('keeps false and null distinct in a partial report', async () => {
    const report = cloneFixture(runReportFixture);
    report.status = 'errored';
    report.verdict = null;
    report.cases[0]!.assertions[0]!.expected = false;
    report.cases[0]!.assertions[0]!.actual = null;
    report.cases[0]!.assertions[0]!.passed = null;
    server.use(
      http.get('/api/v1/test-runs/:runId/report', () =>
        HttpResponse.json(report),
      ),
    );
    const wrapper = mount(RunReportPanel, {
      props: { runId: report.run_id, available: true },
    });
    await vi.waitFor(() => expect(wrapper.text()).toContain('断言复核'));
    expect(wrapper.text()).toContain('false');
    expect(wrapper.text()).toContain('null');
    expect(wrapper.text()).toContain('未判定');
  });

  it.each(['REPORT_NOT_READY', 'REPORT_UNAVAILABLE'])(
    'shows the %s report state',
    async (code) => {
      server.use(
        http.get('/api/v1/test-runs/:runId/report', () =>
          HttpResponse.json(
            {
              error: {
                code,
                message: `错误 ${code}`,
                request_id: 'req_report',
              },
            },
            { status: 409 },
          ),
        ),
      );
      const wrapper = mount(RunReportPanel, {
        props: { runId: 'run_report', available: true },
      });
      await vi.waitFor(() => expect(wrapper.text()).toContain(code));
      expect(wrapper.text()).toContain(`错误 ${code}`);
    },
  );
});
