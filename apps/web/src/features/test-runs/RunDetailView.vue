<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import {
  cancelRun,
  getRun,
  isApiError,
  type PublishedEvent,
  type RunDetail,
} from '../../api';
import EmptyState from '../../components/EmptyState.vue';
import ProgressBar from '../../components/ProgressBar.vue';
import StateBadge from '../../components/StateBadge.vue';
import { terminalEventTypes } from './events';
import {
  formatDate,
  statusLabels,
  terminalStatuses,
  verdictLabels,
} from './presentation';
import RunEventTimeline from './RunEventTimeline.vue';
import { useRunEvents } from './useRunEvents';

const route = useRoute();
const run = ref<RunDetail | null>(null);
const loading = ref(false);
const error = ref('');
const requestId = ref('');
const cancelBusy = ref(false);
const cancelMessage = ref('');
const cancelError = ref('');
let controller: AbortController | null = null;
let cancelController: AbortController | null = null;
let requestSequence = 0;
const verifiedCases = new Set<string>();

const runId = computed(() => String(route.params.runId ?? ''));
const progressPercent = computed(() => {
  const progress = run.value?.progress;
  if (!progress?.total_cases) return 0;
  return Math.min(
    100,
    Math.round((progress.completed_cases / progress.total_cases) * 100),
  );
});
const isTerminal = computed(() =>
  run.value ? terminalStatuses.has(run.value.status) : false,
);
const verdictText = computed(() =>
  run.value?.verdict ? verdictLabels[run.value.verdict] : '未产生',
);
const eventsEnabled = computed(() => run.value?.run_id === runId.value);
const elapsed = computed(() => {
  const { started_at, finished_at } = run.value ?? {};
  if (!started_at || !finished_at) return '—';
  const seconds = (Date.parse(finished_at) - Date.parse(started_at)) / 1000;
  return Number.isFinite(seconds) && seconds >= 0
    ? `${seconds.toFixed(2)} 秒`
    : '—';
});
const localLiveView =
  import.meta.env.VITE_LOCAL_LIVE_VIEW === 'true' &&
  ['127.0.0.1', 'localhost', '[::1]'].includes(window.location.hostname);

async function load(id: string, clear = true): Promise<void> {
  controller?.abort();
  controller = new AbortController();
  const current = ++requestSequence;
  loading.value = true;
  error.value = '';
  requestId.value = '';
  if (clear) run.value = null;
  try {
    const detail = await getRun(id, controller.signal);
    if (current === requestSequence) run.value = detail;
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') return;
    if (current !== requestSequence) return;
    error.value = cause instanceof Error ? cause.message : '读取任务详情失败';
    if (isApiError(cause)) requestId.value = cause.requestId ?? '';
  } finally {
    if (current === requestSequence) loading.value = false;
  }
}

const { events, connectionMessage } = useRunEvents(
  runId,
  eventsEnabled,
  applyRunEvent,
);

function resetCancellation(): void {
  cancelController?.abort();
  cancelController = null;
  cancelBusy.value = false;
  cancelMessage.value = '';
  cancelError.value = '';
}

function applyRunEvent(event: PublishedEvent): void {
  const detail = run.value;
  if (detail?.run_id !== event.run_id || runId.value !== event.run_id) return;
  if (terminalEventTypes.has(event.type)) {
    resetCancellation();
    void load(event.run_id, false);
    return;
  }
  if (event.type === 'run.started') {
    if (detail.status === 'queued') detail.status = 'running';
    detail.started_at ??= event.timestamp;
  }
  const total = event.payload.total_cases;
  if (
    event.type === 'plan.created' &&
    detail.progress.total_cases === null &&
    typeof total === 'number' &&
    Number.isSafeInteger(total) &&
    total >= 0
  ) {
    detail.progress.total_cases = total;
  }
  if (event.type === 'case.verified' && event.case_id) {
    verifiedCases.add(event.case_id);
    detail.progress.completed_cases = Math.max(
      detail.progress.completed_cases,
      verifiedCases.size,
    );
  }
}

async function requestCancel(): Promise<void> {
  const id = runId.value;
  if (run.value?.run_id !== id || cancelBusy.value || isTerminal.value) return;
  const pending = new AbortController();
  cancelController = pending;
  const isCurrent = () => cancelController === pending && runId.value === id;
  cancelBusy.value = true;
  cancelMessage.value = '';
  cancelError.value = '';
  try {
    const result = await cancelRun(id, pending.signal);
    if (!isCurrent() || run.value?.run_id !== id || isTerminal.value) return;
    run.value.status = result.status;
    run.value.cancellation_requested = result.cancellation_requested;
    cancelMessage.value =
      result.status === 'cancelled'
        ? '任务已取消'
        : '取消已请求，正在等待 Worker 完成清理';
    if (result.status === 'cancelled') await load(id, false);
  } catch (cause) {
    if (!isCurrent() || run.value?.run_id !== id || isTerminal.value) return;
    if (isApiError(cause) && cause.code === 'RUN_NOT_CANCELLABLE') {
      cancelMessage.value = '任务状态已经变化，详情已重新同步';
      await load(id, false);
    } else {
      cancelError.value =
        cause instanceof Error ? cause.message : '取消任务失败';
    }
  } finally {
    if (isCurrent()) {
      cancelController = null;
      cancelBusy.value = false;
    }
  }
}

watch(
  runId,
  (id) => {
    resetCancellation();
    verifiedCases.clear();
    return load(id);
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  controller?.abort();
  resetCancellation();
});
</script>

<template>
  <section class="page detail-page">
    <RouterLink class="back-link" to="/runs"
      ><span aria-hidden="true">←</span> 返回运行记录</RouterLink
    >

    <div v-if="loading" class="panel loading-state detail-loading">
      <span class="spinner spinner-dark"></span>正在读取任务详情…
    </div>
    <div v-else-if="error" class="panel error-state" role="alert">
      <span class="error-state-icon" aria-hidden="true">!</span>
      <div>
        <h2>无法读取任务详情</h2>
        <p>{{ error }}</p>
        <small v-if="requestId">请求 ID：{{ requestId }}</small>
      </div>
      <button
        class="button button-secondary"
        type="button"
        @click="load(runId)"
      >
        重试
      </button>
    </div>

    <template v-else-if="run">
      <div class="run-hero">
        <div>
          <h1>{{ run.goal }}</h1>
          <div class="badge-group">
            <StateBadge :tone="run.status" :label="statusLabels[run.status]" />
            <StateBadge
              v-if="run.verdict"
              :tone="run.verdict"
              :label="verdictLabels[run.verdict]"
            />
            <span v-else class="badge badge-neutral"
              ><span class="badge-dot"></span>未产生</span
            >
          </div>
          <div v-if="!isTerminal" class="hero-actions">
            <a
              v-if="localLiveView"
              class="button button-hero"
              href="/live/"
              target="_blank"
              rel="noopener noreferrer"
              >本机浏览器画面</a
            >
            <button
              class="button button-hero"
              type="button"
              :disabled="cancelBusy || run.cancellation_requested"
              @click="requestCancel"
            >
              {{
                cancelBusy
                  ? '正在取消…'
                  : run.cancellation_requested
                    ? '取消已请求'
                    : '取消运行'
              }}
            </button>
          </div>
        </div>
        <div class="hero-progress">
          <div class="progress-value">
            <strong>{{ progressPercent }}</strong
            ><span>%</span>
          </div>
          <ProgressBar :value="progressPercent" />
          <small
            >已完成
            <span
              >{{ run.progress.completed_cases }} /
              {{ run.progress.total_cases ?? '待规划' }}</span
            >
            个用例</small
          >
        </div>
      </div>

      <div
        v-if="run.cancellation_requested && run.status === 'running'"
        class="alert alert-warning"
      >
        <div>
          <strong>取消请求已受理</strong
          ><small>正在等待 Worker 停止运行并完成资源清理。</small>
        </div>
      </div>
      <div v-if="cancelMessage" class="alert alert-warning">
        <strong>{{ cancelMessage }}</strong>
      </div>
      <div v-if="cancelError" class="alert alert-error" role="alert">
        <strong>{{ cancelError }}</strong>
      </div>
      <div v-if="run.error" class="alert alert-error">
        <div>
          <strong>{{ run.error.message }}</strong
          ><small>错误码：{{ run.error.code }}</small>
        </div>
      </div>

      <div class="detail-overview">
        <div>
          <span>运行状态</span><strong>{{ statusLabels[run.status] }}</strong>
        </div>
        <div>
          <span>测试判定</span
          ><strong :class="run.verdict ? `text-${run.verdict}` : ''">{{
            verdictText
          }}</strong>
        </div>
        <div>
          <span>已完成用例</span
          ><strong>{{ run.progress.completed_cases }}</strong>
        </div>
        <div>
          <span>用例总数</span
          ><strong>{{ run.progress.total_cases ?? '待规划' }}</strong>
        </div>
      </div>

      <div class="detail-layout">
        <section class="panel detail-panel" aria-labelledby="run-request-title">
          <div class="panel-title">
            <h2 id="run-request-title">任务信息</h2>
          </div>
          <dl class="detail-list">
            <dt>自然语言测试目标</dt>
            <dd class="detail-request-text">{{ run.goal }}</dd>
            <dt>预期行为</dt>
            <dd class="detail-request-text">{{ run.expected_behavior }}</dd>
            <dt>目标地址</dt>
            <dd>
              <a :href="run.target_url" target="_blank" rel="noreferrer">{{
                run.target_url
              }}</a>
            </dd>
            <dt>Run ID</dt>
            <dd>
              <code>{{ run.run_id }}</code>
            </dd>
            <dt>创建时间</dt>
            <dd>{{ formatDate(run.created_at) }}</dd>
            <dt>开始时间</dt>
            <dd>{{ formatDate(run.started_at) }}</dd>
            <dt>结束时间</dt>
            <dd>{{ formatDate(run.finished_at) }}</dd>
            <dt>运行耗时</dt>
            <dd>{{ elapsed }}</dd>
          </dl>
        </section>
        <div
          v-if="(run.progress.total_cases ?? 0) > 1"
          class="panel detail-panel"
        >
          <div class="panel-title">
            <div>
              <h2>用例汇总</h2>
              <p>仅统计已经获得判定的测试用例。</p>
            </div>
          </div>
          <div v-if="run.summary" class="summary-grid">
            <div class="summary-passed">
              <span>通过</span><b>{{ run.summary.passed }}</b>
            </div>
            <div class="summary-failed">
              <span>失败</span><b>{{ run.summary.failed }}</b>
            </div>
            <div class="summary-blocked">
              <span>受阻</span><b>{{ run.summary.blocked }}</b>
            </div>
            <div class="summary-inconclusive">
              <span>无法判定</span><b>{{ run.summary.inconclusive }}</b>
            </div>
          </div>
          <EmptyState
            v-else
            title="尚无可查询报告"
            description="运行完成后将在这里显示用例统计。"
            icon="◌"
          />
        </div>
        <RunEventTimeline
          :key="run.run_id"
          :run-id="run.run_id"
          :report-available="isTerminal"
          :events="events"
          :connection-message="connectionMessage"
        />
      </div>
    </template>
  </section>
</template>
