import { onBeforeUnmount, ref, watch, type Ref } from 'vue';
import { runEventsUrl, type PublishedEvent } from '../../api';
import { eventTypes, terminalEventTypes } from './events';

type ConnectionState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'complete'
  | 'unavailable'
  | 'error';

export function eventDisposition(
  runId: string,
  cursor: number,
  event: PublishedEvent,
): 'ignore' | 'gap' | 'apply' {
  if (event.run_id !== runId || event.sequence <= cursor) return 'ignore';
  return event.sequence === cursor + 1 ? 'apply' : 'gap';
}

export function useRunEvents(
  runId: Ref<string>,
  enabled: Ref<boolean>,
  onEvent: (event: PublishedEvent) => void,
) {
  const events = ref<PublishedEvent[]>([]);
  const connection = ref<ConnectionState>('idle');
  const connectionMessage = ref('');
  const cursor = ref(0);
  let source: EventSource | null = null;
  let recoveryTimer: number | undefined;
  let activeRunId = '';
  let recoveryAttempts = 0;
  let stopped = false;

  function close(): void {
    source?.close();
    source = null;
    window.clearTimeout(recoveryTimer);
    recoveryTimer = undefined;
  }

  function apply(event: PublishedEvent): void {
    const disposition = eventDisposition(activeRunId, cursor.value, event);
    if (disposition === 'ignore') return;
    if (disposition === 'gap') {
      close();
      if (recoveryAttempts >= 3) {
        connection.value = 'error';
        connectionMessage.value = '事件序号不连续，已停止自动恢复';
        return;
      }
      recoveryAttempts += 1;
      connection.value = 'reconnecting';
      connectionMessage.value = `正在从序号 ${cursor.value} 补读缺失事件`;
      recoveryTimer = window.setTimeout(
        () => connect(event.run_id, cursor.value),
        150,
      );
      return;
    }
    events.value.push(event);
    cursor.value = event.sequence;
    recoveryAttempts = 0;
    if (terminalEventTypes.has(event.type)) {
      close();
      connection.value = 'complete';
      connectionMessage.value = '运行事件已同步';
    }
    onEvent(event);
  }

  function connect(id: string, after = 0): void {
    close();
    if (stopped || !enabled.value || !id) return;
    if (typeof EventSource === 'undefined') {
      connection.value = 'unavailable';
      connectionMessage.value = '当前环境不支持实时事件连接';
      return;
    }
    activeRunId = id;
    connection.value = after ? 'reconnecting' : 'connecting';
    connectionMessage.value = after ? '正在恢复事件连接' : '正在连接事件流';
    const next = new EventSource(runEventsUrl(id, after));
    source = next;
    next.onopen = () => {
      if (source !== next) return;
      connection.value = 'connected';
      connectionMessage.value = '实时事件已连接';
    };
    next.onerror = () => {
      if (source !== next) return;
      if (next.readyState === EventSource.CLOSED) {
        connection.value = 'error';
        connectionMessage.value = '事件流已关闭，可以刷新页面重试';
        close();
        return;
      }
      connection.value = 'reconnecting';
      connectionMessage.value = '连接中断，浏览器正在自动重连';
    };
    for (const type of eventTypes) {
      next.addEventListener(type, (message) => {
        if (source !== next) return;
        try {
          apply(
            JSON.parse(
              (message as MessageEvent<string>).data,
            ) as PublishedEvent,
          );
        } catch {
          connection.value = 'error';
          connectionMessage.value = '收到无法解析的事件数据';
        }
      });
    }
  }

  function restart(id: string): void {
    close();
    events.value = [];
    cursor.value = 0;
    recoveryAttempts = 0;
    connectionMessage.value = '';
    connect(id, 0);
  }

  watch(
    [runId, enabled],
    ([id, shouldConnect]) => {
      if (shouldConnect) restart(id);
      else {
        close();
        connection.value = 'idle';
      }
    },
    { immediate: true },
  );

  onBeforeUnmount(() => {
    stopped = true;
    close();
  });

  return { events, connection, connectionMessage, cursor, restart, close };
}
