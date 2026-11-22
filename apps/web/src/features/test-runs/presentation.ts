import type { RunStatus, Verdict } from '../../api';

export const statusLabels: Record<RunStatus, string> = {
  queued: '排队中',
  running: '运行中',
  succeeded: '正常完成',
  errored: '执行错误',
  cancelled: '已取消',
};

export const verdictLabels: Record<Verdict, string> = {
  passed: '通过',
  failed: '发现失败',
  blocked: '受阻',
  inconclusive: '无法判定',
};

export function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '—';
}

export function formatError(error: unknown): string {
  return error instanceof Error ? error.message : '发生未知错误';
}
