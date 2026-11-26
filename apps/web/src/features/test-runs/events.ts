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
  'case.started',
  'case.verified',
  ...terminalEventTypes,
]);

export const actionLabels: Record<string, string> = {
  'browser.navigate': '打开页面',
  'browser.click': '点击控件',
  'browser.fill': '填写字段',
  'browser.select_option': '选择选项',
};

export const toolLabels: Record<string, string> = {
  ...actionLabels,
  'browser.observe': '读取页面',
  'browser.inspect': '检查页面',
  'browser.screenshot': '保存截图',
};

const conditionLabels: Record<string, string> = {
  url_equals: '核对页面地址',
  url_path_starts_with: '核对页面位置',
  title_equals: '核对浏览器标签页标题',
  exists: '确认元素存在',
  visible: '确认内容可见',
  count: '核对元素数量',
  text_equals: '核对显示的文字是否完全一致',
};

const failureExplanations: Record<string, string> = {
  AMBIGUOUS_LOCATOR: '匹配到多个元素，浏览器没有对其中任何一个执行操作。',
  ELEMENT_NOT_FOUND: '页面上没有匹配的元素。',
  INVALID_ARGUMENTS: '工具收到的参数不符合要求。',
  ELEMENT_NOT_INTERACTABLE: '控件当前不可操作。',
  TOOL_TIMEOUT: '操作未在时限内完成。',
  ARTIFACT_WRITE_FAILED: '采集到的证据无法保存。',
  ACTION_NOT_ALLOWED: '当前页面状态或目标策略禁止这次操作。',
};

interface ToolDetail {
  phase?: 'start' | 'check' | 'result';
  condition?: string;
  target?: string;
  destination?: string;
  matched?: boolean;
  screenshot_id?: string;
}

function toolDetail(event: PublishedEvent): ToolDetail {
  return (event.payload.detail ?? {}) as ToolDetail;
}

export function screenshotIds(event: PublishedEvent): string[] {
  if (event.type !== 'tool.completed' || event.payload.success !== true)
    return [];
  const screenshotId = toolDetail(event).screenshot_id;
  return evidenceIds(event).filter(
    (id) => event.payload.tool === 'browser.screenshot' || id === screenshotId,
  );
}

export function evidenceIds(event: PublishedEvent): string[] {
  if (
    event.type === 'report.generated' &&
    typeof event.payload.artifact_id === 'string'
  )
    return [event.payload.artifact_id];
  const ids = event.payload.evidence_ids;
  return Array.isArray(ids)
    ? ids.filter((id): id is string => typeof id === 'string')
    : [];
}

interface TimelineEntry {
  event: PublishedEvent;
  count: number;
  followUp?: string;
}

function recoveryDescription(failed: PublishedEvent, next: PublishedEvent) {
  if (
    failed.case_id !== next.case_id ||
    failed.type !== 'tool.completed' ||
    failed.payload.success !== false ||
    next.payload.success !== true
  )
    return;
  const before = toolDetail(failed);
  const after = toolDetail(next);
  if (
    failed.payload.tool === 'browser.click' &&
    failed.payload.error_code === 'AMBIGUOUS_LOCATOR' &&
    next.payload.tool === 'browser.navigate'
  ) {
    if (before.destination && before.destination === after.destination)
      return '随后直接打开了链接对应的页面，避开了多个匹配项。';
    if (!before.destination) return '随后改用页面导航并成功打开页面。';
  }
  if (
    failed.payload.tool === next.payload.tool &&
    (before.target || before.destination) &&
    before.target === after.target &&
    before.condition === after.condition &&
    before.destination === after.destination &&
    after.matched !== false
  )
    return '随后对同一目标的操作成功。';
}

export function summarizeTimeline(events: PublishedEvent[]): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  let previousTool: TimelineEntry | undefined;
  for (const event of events) {
    const hasEvidence = evidenceIds(event).length > 0;
    if (
      progressEventTypes.has(event.type) ||
      (event.type === 'report.generated' && hasEvidence)
    ) {
      entries.push({ event, count: 1 });
      previousTool = undefined;
      continue;
    }
    if (event.type !== 'tool.completed') continue;

    const previous = entries.at(-1);
    const failure = event.payload.success === false;
    const detail = toolDetail(event);
    const followUp =
      previousTool && recoveryDescription(previousTool.event, event);
    const tool = String(event.payload.tool);
    if (
      !failure &&
      !Object.hasOwn(actionLabels, tool) &&
      !hasEvidence &&
      !(tool === 'browser.inspect' && detail.phase) &&
      !followUp
    )
      continue;

    if (followUp && previousTool) previousTool.followUp = followUp;
    if (
      failure &&
      !hasEvidence &&
      previous &&
      !evidenceIds(previous.event).length &&
      previous?.event.type === 'tool.completed' &&
      previous.event.payload.success === false &&
      previous.event.case_id === event.case_id &&
      previous.event.payload.tool === tool &&
      previous.event.payload.error_code === event.payload.error_code &&
      JSON.stringify(toolDetail(previous.event)) === JSON.stringify(detail)
    ) {
      previous.count += 1;
      continue;
    }
    const entry = { event, count: 1 };
    entries.push(entry);
    if (failure || tool !== 'browser.observe') previousTool = entry;
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
    return 'warning';
  return 'neutral';
}

export function timelineTitle(event: PublishedEvent): string {
  if (event.type !== 'tool.completed')
    return eventLabels[event.type] ?? event.type;
  const tool = String(event.payload.tool);
  const { phase } = toolDetail(event);
  const action =
    tool === 'browser.inspect' && phase === 'result'
      ? '复核测试结果'
      : tool === 'browser.inspect' && phase === 'check'
        ? '确认是否还有待完成的目标'
        : tool === 'browser.screenshot' && phase === 'result'
          ? '保存结果截图'
          : phase === 'start'
            ? '打开测试起始页'
            : (toolLabels[tool] ?? '执行工具');
  return event.payload.success === false ? `${action}失败` : action;
}

export function stepSummary(summary: unknown): string | null {
  return typeof summary === 'string' &&
    summary !== 'Observe and exercise the test case'
    ? summary
    : null;
}

function toolPurpose(event: PublishedEvent): string {
  const { condition, target, destination, phase } = toolDetail(event);
  const label = target ? `「${target}」` : '';
  switch (event.payload.tool) {
    case 'browser.navigate':
      return `打开${label || '页面'}${destination ? `（${destination}）` : ''}。`;
    case 'browser.click':
      return `操作${label || '页面上的控件'}。`;
    case 'browser.fill':
      return `向${label || '表单字段'}输入测试数据。`;
    case 'browser.select_option':
      return `在${label || '下拉框'}中选择所需选项。`;
    case 'browser.inspect':
      return `${conditionLabels[condition ?? ''] ?? '检查页面内容'}${label}。`;
    case 'browser.screenshot':
      return phase === 'result'
        ? '记录断言复核结束时的页面。'
        : '保存当前页面画面，供人工核对。';
    case 'browser.observe':
      return screenshotIds(event).length
        ? '同时保存当前页面画面，供人工核对。'
        : '读取页面上可以使用的链接和控件。';
    default:
      return '';
  }
}

export function eventSummary(event: PublishedEvent): string {
  const payload = event.payload;
  switch (event.type) {
    case 'plan.created':
      return `计划包含 ${String(payload.total_cases)} 个测试用例`;
    case 'case.started':
      return String(payload.name ?? event.case_id ?? '未命名用例');
    case 'agent.step.started':
      return stepSummary(payload.summary) ?? '开始下一轮浏览器操作';
    case 'tool.called':
      return toolLabels[String(payload.tool)] ?? '调用浏览器工具';
    case 'tool.completed': {
      const { matched } = toolDetail(event);
      const purpose = toolPurpose(event);
      if (payload.success === false) {
        const code = String(payload.error_code ?? '失败');
        return `${purpose}${failureExplanations[code] ?? '工具操作未完成。'}`;
      }
      if (typeof matched === 'boolean')
        return `${purpose}${matched ? '符合预期。' : '当前状态与预期不符。'}`;
      return purpose || '已完成。';
    }
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
