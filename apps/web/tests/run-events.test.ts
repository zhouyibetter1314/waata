import { describe, expect, it } from 'vitest';
import type { PublishedEvent } from '../src/api';
import { terminalEventTypes } from '../src/features/test-runs/events';
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
