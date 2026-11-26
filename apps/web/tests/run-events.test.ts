import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import type { PublishedEvent } from '../src/api';
import { terminalEventTypes } from '../src/features/test-runs/events';
import RunEventTimeline from '../src/features/test-runs/RunEventTimeline.vue';
import { eventDisposition } from '../src/features/test-runs/useRunEvents';

function event(sequence: number, runId = 'run_001'): PublishedEvent {
  return {
    schema_version: 1,
    event_id: `evt_${sequence}`,
    run_id: runId,
    sequence,
    type: 'tool.completed',
    timestamp: '2026-11-21T02:00:00Z',
    case_id: 'case_001',
    step_id: 'step_001',
    payload: {},
  };
}

describe('F04 C4 event ordering', () => {
  it('applies only the next contiguous event', () => {
    expect(eventDisposition('run_001', 4, event(5))).toBe('apply');
  });

  it('deduplicates old sequences and isolates runs', () => {
    expect(eventDisposition('run_001', 4, event(4))).toBe('ignore');
    expect(eventDisposition('run_001', 4, event(5, 'run_other'))).toBe(
      'ignore',
    );
  });

  it('detects a sequence gap for bounded recovery', () => {
    expect(eventDisposition('run_001', 4, event(7))).toBe('gap');
  });

  it('recognizes every C4 terminal event', () => {
    expect([...terminalEventTypes]).toEqual([
      'run.completed',
      'run.failed',
      'run.cancelled',
    ]);
  });
});

describe('Run timeline', () => {
  it('summarizes progress and repeated failures and can show the original stream', async () => {
    const failed = {
      tool: 'browser.inspect',
      success: false,
      error_code: 'ELEMENT_NOT_FOUND',
    };
    const wrapper = mount(RunEventTimeline, {
      props: {
        connectionMessage: '运行事件已同步',
        events: [
          { ...event(1), type: 'run.started' },
          { ...event(2), type: 'agent.step.started' },
          { ...event(3), type: 'tool.called' },
          { ...event(4), payload: failed },
          { ...event(5), payload: failed },
          { ...event(6), payload: { tool: 'browser.observe', success: true } },
          { ...event(7), type: 'report.generated' },
          {
            ...event(8),
            type: 'run.completed',
            payload: { verdict: 'inconclusive' },
          },
        ],
      },
    });
    expect(wrapper.findAll('li')).toHaveLength(3);
    expect(wrapper.text()).toContain('ELEMENT_NOT_FOUND · 2 次');
    expect(wrapper.text()).toContain('任务正常完成');
    expect(wrapper.find('details').exists()).toBe(false);

    const toggle = wrapper.get('button');
    await toggle.trigger('click');
    expect(toggle.attributes('aria-expanded')).toBe('true');
    expect(wrapper.findAll('li')).toHaveLength(8);
    expect(
      wrapper.findAll('li').map((row) => row.get('.event-index').text()),
    ).toEqual(['1', '2', '3', '4', '5', '6', '7', '8']);
    expect(wrapper.findAll('details')).toHaveLength(8);
    await toggle.trigger('click');
    expect(wrapper.findAll('li')).toHaveLength(3);
  });

  it('explains a link recovery in order and connects the final check to its screenshot', () => {
    const destination = 'http://127.0.0.1:4200/c/waata-lab/5';
    const wrapper = mount(RunEventTimeline, {
      props: {
        connectionMessage: '运行事件已同步',
        events: [
          {
            ...event(1),
            payload: {
              tool: 'browser.click',
              success: false,
              error_code: 'AMBIGUOUS_LOCATOR',
              detail: { target: 'WAATA Lab', destination },
            },
          },
          { ...event(2), payload: { tool: 'browser.observe', success: true } },
          {
            ...event(3),
            payload: {
              tool: 'browser.navigate',
              success: true,
              detail: { target: 'WAATA Lab', destination },
            },
          },
          {
            ...event(4),
            payload: {
              tool: 'browser.inspect',
              success: true,
              detail: {
                target: 'First post text',
                phase: 'result',
                condition: 'text_equals',
                matched: true,
              },
            },
          },
          {
            ...event(5),
            payload: {
              tool: 'browser.screenshot',
              success: true,
              evidence_ids: ['art_result'],
              detail: { phase: 'result', screenshot_id: 'art_result' },
            },
          },
        ],
      },
    });
    const rows = wrapper.findAll('li');
    expect(rows).toHaveLength(4);
    expect(rows[0]?.text()).toContain('匹配到多个元素');
    expect(rows[0]?.text()).toContain('随后直接打开了链接对应的页面');
    expect(rows[1]?.text()).toContain('打开「WAATA Lab」');
    expect(rows[2]?.text()).toContain('核对显示的文字是否完全一致');
    expect(rows[2]?.text()).toContain('符合预期');
    expect(rows[3]?.text()).toContain('保存结果截图');
    expect(rows[3]?.get('button').text()).toBe('查看本步截图');
  });
});
