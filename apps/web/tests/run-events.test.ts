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
});
