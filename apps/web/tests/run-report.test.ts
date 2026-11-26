import { mount } from '@vue/test-utils';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import RunReportPanel from '../src/features/test-runs/RunReportPanel.vue';
import { cloneFixture, runReportFixture } from './fixtures/api';
import { server } from './fixtures/server';

describe('F06 report and evidence', () => {
  it.each(['failed', 'inconclusive', 'errored'] as const)(
    'groups screenshots and handles missing evidence for %s runs',
    async (state) => {
      const report = cloneFixture(runReportFixture);
      report.status = state === 'errored' ? 'errored' : 'succeeded';
      report.verdict = state === 'errored' ? null : state;
      const testCase = report.cases[0]!;
      report.cases.push({ ...testCase, case_id: 'case_empty', name: 'B02' });
      const screenshot = {
        ...report.artifacts[0]!,
        run_id: report.run_id,
        case_id: testCase.case_id,
        artifact_id: 'art_screenshot',
        mime_type: 'image/png',
        kind: 'screenshot' as const,
      };
      report.artifacts.push(screenshot);
      server.use(
        http.get('/api/v1/test-runs/:runId/report', () =>
          HttpResponse.json(report),
        ),
      );
      const wrapper = mount(RunReportPanel, {
        props: { runId: report.run_id, available: true },
      });
      await vi.waitFor(() =>
        expect(wrapper.find('.screenshot-card img').exists()).toBe(true),
      );
      expect(wrapper.get('.screenshot-card img').attributes('src')).toContain(
        '/artifacts/art_screenshot',
      );
      expect(wrapper.get('.screenshot-card').text()).toContain(
        testCase.case_id,
      );
      expect(
        wrapper.get('.screenshot-card a[download]').attributes('download'),
      ).toBe('art_screenshot.png');
      expect(wrapper.get('.screenshot-evidence').text()).toContain(
        '此用例尚无截图',
      );
      await wrapper.get('.screenshot-card img').trigger('error');
      expect(wrapper.find('.screenshot-card img').exists()).toBe(false);
      expect(wrapper.get('.screenshot-card').text()).toContain('截图暂不可用');
      wrapper.unmount();
    },
  );
  it('explains a failed report with no saved evidence', async () => {
    const report = cloneFixture(runReportFixture);
    report.status = 'errored';
    report.verdict = null;
    report.error = {
      code: 'INTERNAL_ERROR',
      message: 'The model hit its output limit before finishing the test plan',
    };
    report.cases = [];
    report.artifacts = [];
    server.use(
      http.get('/api/v1/test-runs/:runId/report', () =>
        HttpResponse.json(report),
      ),
    );
    const wrapper = mount(RunReportPanel, {
      props: { runId: report.run_id, available: true },
    });
    await vi.waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toContain(
        'The model hit its output limit',
      ),
    );
    expect(wrapper.text()).toContain('没有已保存的截图或其他证据');
    expect(wrapper.text()).toContain('没有可复核的用例');
  });

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
    expect(wrapper.text()).toContain('否');
    expect(wrapper.text()).toContain('未记录');
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
