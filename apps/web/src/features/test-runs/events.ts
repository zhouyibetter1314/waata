import type { PublishedEvent, Verdict } from '../../api';
import { verdictLabels } from './presentation';

export const eventTypes = [
  'run.started',
  'plan.created',
  'case.started',
  'agent.step.started',
  'tool.called',
  'tool.completed',
  'case.verified',
  'report.generated',
  'run.completed',
  'run.failed',
  'run.cancelled',
] as const;

export const terminalEventTypes = new Set([
  'run.completed',
  'run.failed',
  'run.cancelled',
]);

const progressEventTypes = new Set([
  'run.started',
  'plan.created',
  'case.started',
  'case.verified',
  ...terminalEventTypes,
]);

export function summarizeTimeline(events: PublishedEvent[]) {
  const entries: { event: PublishedEvent; count: number }[] = [];
  const failures = new Map<string, (typeof entries)[number]>();
  for (const event of events) {
    if (
      progressEventTypes.has(event.type) ||
      (event.type === 'tool.completed' &&
        event.payload.tool === 'browser.screenshot' &&
        event.payload.success === true)
    ) {
      entries.push({ event, count: 1 });
    } else if (
      event.type === 'tool.completed' &&
      event.payload.success === false
    ) {
      const key = JSON.stringify([
        event.case_id,
        event.payload.tool,
        event.payload.error_code,
      ]);
      const earlier = failures.get(key);
      if (earlier) {
        earlier.count += 1;
      } else {
        const entry = { event, count: 1 };
        failures.set(key, entry);
        entries.push(entry);
      }
    }
  }
  return entries;
}

export const eventLabels: Record<string, string> = {
  'run.started': '任务开始运行',
  'plan.created': '测试计划已生成',
  'case.started': '测试用例开始',
  'agent.step.started': '执行测试步骤',
  'tool.called': '调用浏览器工具',
  'tool.completed': '浏览器工具完成',
  'case.verified': '用例判定完成',
  'report.generated': '结构化报告已生成',
  'run.completed': '任务正常完成',
  'run.failed': '任务执行错误',
  'run.cancelled': '任务已取消',
};

export function eventTone(event: PublishedEvent): string {
  if (event.type === 'run.failed') return 'danger';
  if (event.type === 'run.cancelled') return 'warning';
  if (event.type === 'run.completed' || event.type === 'report.generated')
    return 'success';
  if (event.type === 'tool.completed' && event.payload.success === false)
    return 'danger';
  return 'neutral';
}

export function eventSummary(event: PublishedEvent): string {
  const payload = event.payload;
  switch (event.type) {
    case 'plan.created':
      return `计划包含 ${String(payload.total_cases)} 个测试用例`;
    case 'case.started':
      return String(payload.name ?? event.case_id ?? '未命名用例');
    case 'agent.step.started':
      return String(payload.summary ?? '开始执行下一步操作');
    case 'tool.called':
      return `调用 ${String(payload.tool)}`;
    case 'tool.completed':
      return payload.success
        ? `${String(payload.tool)} · ${String(payload.duration_ms)} ms`
        : `${String(payload.tool)} · ${String(payload.error_code ?? '失败')}`;
    case 'case.verified':
    case 'run.completed':
      return verdictLabels[payload.verdict as Verdict] ?? '未判定';
    case 'report.generated':
      return '报告已经可以查询';
    case 'run.failed':
      return (
        (payload.error as { code?: string } | undefined)?.code ?? '未知错误'
      );
    case 'run.cancelled':
      return '取消已生效，运行资源已完成清理';
    default:
      return event.type === 'run.started'
        ? 'Worker 已领取任务并开始执行'
        : '事件已记录';
  }
}
