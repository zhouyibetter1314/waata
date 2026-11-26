<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import EmptyState from '../../components/EmptyState.vue';
import StateBadge from '../../components/StateBadge.vue';
import {
  deleteRun,
  isApiError,
  type RunStatus,
  type RunSummary,
} from '../../api';
import { useTestRunsStore } from './store';
import {
  formatDate,
  formatError,
  statusLabels,
  verdictLabels,
} from './presentation';
import { terminalStatuses } from './presentation';

const store = useTestRunsStore();
const search = ref('');
const statusFilter = ref<RunStatus | ''>('');
const deleting = ref('');
const deletionError = ref('');
const deletionNotice = ref('');
const totalPages = computed(() =>
  Math.max(1, Math.ceil(store.total / store.pageSize)),
);
const visibleItems = computed(() => {
  const query = search.value.trim().toLocaleLowerCase('zh-CN');
  return store.items.filter((run) => {
    const matchesStatus =
      !statusFilter.value || run.status === statusFilter.value;
    const matchesSearch =
      !query ||
      run.goal.toLocaleLowerCase('zh-CN').includes(query) ||
      run.target_url.toLocaleLowerCase('zh-CN').includes(query) ||
      run.run_id.toLocaleLowerCase('zh-CN').includes(query);
    return matchesStatus && matchesSearch;
  });
});
const currentPageCompleted = computed(
  () => store.items.filter((run) => run.status === 'succeeded').length,
);
const currentPageActive = computed(
  () =>
    store.items.filter((run) => ['queued', 'running'].includes(run.status))
      .length,
);
const currentPageIssues = computed(
  () =>
    store.items.filter((run) => ['errored', 'cancelled'].includes(run.status))
      .length,
);

onMounted(() => store.load(1));

async function remove(run: RunSummary): Promise<void> {
  if (
    deleting.value ||
    !window.confirm(
      `确定删除此测试任务及其运行记录和证据？删除后无法恢复。\n\n${run.goal}`,
    )
  )
    return;
  deletionError.value = '';
  deletionNotice.value = '';
  deleting.value = run.run_id;
  try {
    try {
      await deleteRun(run.run_id);
    } catch (error) {
      if (!isApiError(error) || error.code !== 'RUN_NOT_FOUND') throw error;
    }
    store.items = store.items.filter((item) => item.run_id !== run.run_id);
    await store.load(store.page);
    if (!store.error && !store.items.length && store.page > totalPages.value)
      await store.load(totalPages.value);
    deletionNotice.value = '测试任务已删除。';
  } catch (error) {
    deletionError.value = formatError(error);
  } finally {
    deleting.value = '';
  }
}
</script>

<template>
  <section class="page">
    <div class="page-heading">
      <div>
        <div class="eyebrow">EXECUTION ARCHIVE</div>
        <h1>运行与报告</h1>
        <p class="lead">
          查看所有测试任务的生命周期状态和业务判定，按 Run ID 追踪执行结果。
        </p>
      </div>
      <RouterLink class="button button-primary" to="/runs/new">
        <span aria-hidden="true">＋</span> 创建测试
      </RouterLink>
    </div>

    <div class="overview-grid" aria-label="当前页运行概览">
      <div class="overview-card">
        <span class="overview-icon icon-neutral">▦</span>
        <div>
          <strong>{{ store.total }}</strong
          ><span>全部任务</span>
        </div>
      </div>
      <div class="overview-card">
        <span class="overview-icon icon-active">↻</span>
        <div>
          <strong>{{ currentPageActive }}</strong
          ><span>排队或运行中</span>
        </div>
      </div>
      <div class="overview-card">
        <span class="overview-icon icon-success">✓</span>
        <div>
          <strong>{{ currentPageCompleted }}</strong
          ><span>正常完成</span>
        </div>
      </div>
      <div class="overview-card">
        <span class="overview-icon icon-danger">!</span>
        <div>
          <strong>{{ currentPageIssues }}</strong
          ><span>错误或取消</span>
        </div>
      </div>
    </div>

    <p v-if="deletionError" class="alert alert-error" role="alert">
      {{ deletionError }}
    </p>
    <p v-if="deletionNotice" role="status">{{ deletionNotice }}</p>
    <div v-if="store.error" class="alert alert-error" role="alert">
      <div>
        <strong>{{ store.error }}</strong
        ><small>任务列表未能更新，请稍后重试。</small>
      </div>
      <button
        class="button button-quiet"
        type="button"
        @click="store.load(store.page)"
      >
        重试
      </button>
    </div>

    <div class="panel table-panel" :aria-busy="store.loading">
      <div class="panel-toolbar">
        <div>
          <h2>运行历史</h2>
          <p>状态表示执行生命周期，判定表示测试结果，二者相互独立。</p>
        </div>
        <div class="toolbar-actions">
          <label class="search-field">
            <span aria-hidden="true">⌕</span>
            <span class="sr-only">搜索任务</span>
            <input
              v-model="search"
              type="search"
              placeholder="搜索目标、地址或 Run ID"
            />
          </label>
          <label>
            <span class="sr-only">筛选运行状态</span>
            <select v-model="statusFilter">
              <option value="">全部状态</option>
              <option
                v-for="(label, value) in statusLabels"
                :key="value"
                :value="value"
              >
                {{ label }}
              </option>
            </select>
          </label>
          <button
            class="button icon-button"
            type="button"
            title="刷新记录"
            aria-label="刷新记录"
            :disabled="store.loading"
            @click="store.load(store.page)"
          >
            ↻
          </button>
        </div>
      </div>

      <div v-if="store.loading" class="loading-state">
        <span class="spinner spinner-dark"></span>正在加载任务…
      </div>
      <EmptyState
        v-else-if="!store.error && !store.items.length"
        title="还没有测试任务"
        description="创建第一个自然语言 Web 测试任务，运行记录会显示在这里。"
        icon="＋"
      >
        <RouterLink class="button button-primary" to="/runs/new"
          >创建任务</RouterLink
        >
      </EmptyState>
      <EmptyState
        v-else-if="!store.error && !visibleItems.length"
        title="没有匹配的任务"
        description="请调整搜索内容或状态筛选。"
        icon="⌕"
      >
        <button
          class="button button-secondary"
          type="button"
          @click="
            search = '';
            statusFilter = '';
          "
        >
          清除筛选
        </button>
      </EmptyState>
      <div v-else-if="visibleItems.length" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>测试任务</th>
              <th>运行状态</th>
              <th>测试判定</th>
              <th>创建时间</th>
              <th><span class="sr-only">操作</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in visibleItems" :key="run.run_id">
              <td class="run-title-cell">
                <RouterLink :to="`/runs/${encodeURIComponent(run.run_id)}`">{{
                  run.goal
                }}</RouterLink>
                <span>{{ run.target_url }}</span>
                <small>{{ run.run_id }}</small>
              </td>
              <td>
                <StateBadge
                  :tone="run.status"
                  :label="statusLabels[run.status]"
                />
              </td>
              <td>
                <StateBadge
                  v-if="run.verdict"
                  :tone="run.verdict"
                  :label="verdictLabels[run.verdict]"
                />
                <span v-else class="pending-value">— 未产生</span>
              </td>
              <td class="date-cell">{{ formatDate(run.created_at) }}</td>
              <td class="row-action">
                <button
                  v-if="terminalStatuses.has(run.status)"
                  class="text-button text-failed"
                  type="button"
                  :disabled="Boolean(deleting)"
                  @click="remove(run)"
                >
                  {{ deleting === run.run_id ? '正在删除…' : '删除' }}
                </button>
                <RouterLink
                  :to="`/runs/${encodeURIComponent(run.run_id)}`"
                  aria-label="查看任务详情"
                  >→</RouterLink
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <nav v-if="store.total" class="pagination" aria-label="任务分页">
      <button
        class="button button-secondary"
        :disabled="store.page <= 1"
        @click="store.load(store.page - 1)"
      >
        上一页
      </button>
      <span
        >第 {{ store.page }} / {{ totalPages }} 页，共
        {{ store.total }} 条</span
      >
      <button
        class="button button-secondary"
        :disabled="store.page >= totalPages"
        @click="store.load(store.page + 1)"
      >
        下一页
      </button>
    </nav>
  </section>
</template>
