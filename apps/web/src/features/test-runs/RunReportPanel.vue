<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { getRunReport, type PublishedEvent, type RunReport } from '../../api';
import StateBadge from '../../components/StateBadge.vue';
import { evidenceIds } from './events';
import { formatError, verdictLabels } from './presentation';

const props = defineProps<{
  runId: string;
  available: boolean;
  events?: PublishedEvent[];
}>();
const emit = defineEmits<{ evidence: [title: string, ids: string[]] }>();
const report = ref<RunReport | null>(null);
const loading = ref(false);
const error = ref('');
const attempt = ref(0);
const additionalEvidence = computed(() => {
  const linked = new Set((props.events ?? []).flatMap(evidenceIds));
  for (const testCase of report.value?.cases ?? []) {
    for (const assertion of testCase.assertions) {
      for (const id of assertion.evidence_ids) linked.add(id);
    }
  }
  return (
    report.value?.artifacts
      .filter((artifact) => !linked.has(artifact.artifact_id))
      .map((artifact) => artifact.artifact_id) ?? []
  );
});

function displayValue(value: unknown): string {
  if (value === null) return '未记录';
  if (value === true) return '是';
  if (value === false) return '否';
  return typeof value === 'string' ? value : JSON.stringify(value);
}

watch(
  () => [props.runId, props.available, attempt.value] as const,
  async ([id, available], _, onCleanup) => {
    const controller = new AbortController();
    onCleanup(() => controller.abort());
    report.value = null;
    error.value = '';
    loading.value = available;
    if (!available) return;
    try {
      const result = await getRunReport(id, controller.signal);
      if (!controller.signal.aborted) report.value = result;
    } catch (cause) {
      if (!controller.signal.aborted) error.value = formatError(cause);
    } finally {
      if (!controller.signal.aborted) loading.value = false;
    }
  },
  { immediate: true },
);
</script>

<template>
  <details v-if="available" class="timeline-report">
    <summary>查看测试报告</summary>
    <p v-if="loading" role="status">正在加载测试报告…</p>
    <div v-else-if="error" role="alert">
      <p>{{ error }}</p>
      <button class="text-button" type="button" @click="attempt += 1">
        重新查询
      </button>
    </div>
    <template v-else-if="report">
      <p v-if="report.error" role="alert">{{ report.error.message }}</p>
      <p v-if="!report.cases.length">此任务没有可复核的用例。</p>
      <article
        v-for="testCase in report.cases"
        :key="testCase.case_id"
        class="report-case"
      >
        <header>
          <h3>{{ testCase.name }}</h3>
          <StateBadge
            v-if="testCase.verdict"
            :tone="testCase.verdict"
            :label="verdictLabels[testCase.verdict]"
          />
          <span v-else>未判定</span>
        </header>
        <p>{{ testCase.expected_behavior }}</p>
        <p v-if="testCase.reason">{{ testCase.reason }}</p>
        <ul v-if="testCase.preconditions.length">
          <li v-for="(item, index) in testCase.preconditions" :key="index">
            {{ item }}
          </li>
        </ul>
        <h4>断言复核（{{ testCase.assertions.length }}）</h4>
        <div
          v-for="(assertion, index) in testCase.assertions"
          :key="assertion.assertion_id"
          class="assertion-row"
        >
          <div>
            <strong>检查项 {{ index + 1 }}</strong>
            <span>{{
              assertion.passed === null
                ? '未判定'
                : assertion.passed
                  ? '通过'
                  : '未通过'
            }}</span>
          </div>
          <dl>
            <dt>预期</dt>
            <dd>{{ displayValue(assertion.expected) }}</dd>
            <dt>实际</dt>
            <dd>{{ displayValue(assertion.actual) }}</dd>
          </dl>
          <button
            v-if="assertion.evidence_ids.length"
            class="text-button"
            type="button"
            @click="
              emit('evidence', `检查项 ${index + 1}`, assertion.evidence_ids)
            "
          >
            查看证据
          </button>
        </div>
      </article>
      <button
        v-if="additionalEvidence.length"
        class="text-button"
        type="button"
        @click="emit('evidence', '补充证据', additionalEvidence)"
      >
        查看补充证据（{{ additionalEvidence.length }}）
      </button>
    </template>
  </details>
</template>
