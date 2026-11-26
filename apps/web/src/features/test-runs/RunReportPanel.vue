<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import {
  artifactUrl,
  getRunReport,
  type ArtifactView,
  type PublishedEvent,
  type RunReport,
} from '../../api';
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
const screenshotDialog = ref<HTMLDialogElement | null>(null);
const selectedScreenshot = ref<ArtifactView | null>(null);
const unavailableScreenshots = ref(new Set<string>());
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

const screenshotGroups = computed(() => {
  const current = report.value;
  if (!current) return [];
  const screenshots = current.artifacts.filter(
    (item) => item.kind === 'screenshot' && item.run_id === current.run_id,
  );
  const groups = current.cases.map((testCase) => ({
    id: testCase.case_id,
    name: testCase.name,
    screenshots: screenshots.filter(
      (item) => item.case_id === testCase.case_id,
    ),
  }));
  const knownCases = new Set(groups.map((group) => group.id));
  const ungrouped = screenshots.filter(
    (item) => !knownCases.has(item.case_id ?? ''),
  );
  if (ungrouped.length) {
    groups.push({
      id: '__ungrouped',
      name: '未关联用例的截图',
      screenshots: ungrouped,
    });
  }
  return groups;
});

function showScreenshot(artifact: ArtifactView): void {
  selectedScreenshot.value = artifact;
  screenshotDialog.value?.showModal();
}

function markUnavailable(artifactId: string): void {
  unavailableScreenshots.value.add(artifactId);
}

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
    screenshotDialog.value?.close();
    selectedScreenshot.value = null;
    unavailableScreenshots.value.clear();
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
      <div v-if="report.error" class="alert alert-error" role="alert">
        <strong>{{ report.error.message }}</strong>
        <small>{{ report.error.code }}</small>
      </div>
      <p v-if="!report.artifacts.length" class="empty-copy">
        此报告没有已保存的截图或其他证据。
      </p>
      <div class="report-summary">
        <div>
          <span>报告状态</span><strong>{{ report.status }}</strong>
        </div>
        <div>
          <span>总体判定</span
          ><StateBadge
            v-if="report.verdict"
            :tone="report.verdict"
            :label="verdictLabels[report.verdict]"
          /><strong v-else>null</strong>
        </div>
        <div>
          <span>测试用例</span><strong>{{ report.cases.length }}</strong>
        </div>
        <div>
          <span>证据产物</span><strong>{{ report.artifacts.length }}</strong>
        </div>
      </div>

      <section
        class="screenshot-evidence"
        aria-labelledby="screenshot-evidence-title"
      >
        <h3 id="screenshot-evidence-title">截图证据</h3>
        <p v-if="!screenshotGroups.length" class="empty-copy">
          此运行没有已保存的截图。
        </p>
        <section
          v-for="group in screenshotGroups"
          :key="group.id"
          class="screenshot-case"
        >
          <h4>{{ group.name }}</h4>
          <p v-if="!group.screenshots.length" class="empty-copy">
            此用例尚无截图。
          </p>
          <div v-else class="screenshot-grid">
            <article
              v-for="artifact in group.screenshots"
              :key="artifact.artifact_id"
              class="screenshot-card"
            >
              <p
                v-if="unavailableScreenshots.has(artifact.artifact_id)"
                class="empty-copy"
              >
                截图暂不可用，可能已过期或无权访问。
              </p>
              <template v-else>
                <button
                  type="button"
                  class="screenshot-thumbnail"
                  :aria-label="`放大 ${group.name} 截图`"
                  @click="showScreenshot(artifact)"
                >
                  <img
                    :src="artifactUrl(artifact.artifact_id)"
                    :alt="`${group.name} 截图`"
                    @error="markUnavailable(artifact.artifact_id)"
                  />
                </button>
                <div class="evidence-links">
                  <a
                    class="text-button"
                    :href="artifactUrl(artifact.artifact_id)"
                    target="_blank"
                    rel="noopener noreferrer"
                    >查看原图</a
                  >
                  <a
                    class="text-button"
                    :href="artifactUrl(artifact.artifact_id)"
                    :download="`${artifact.artifact_id}.png`"
                    >下载截图</a
                  >
                </div>
              </template>
              <dl class="screenshot-metadata">
                <dt>Run</dt>
                <dd>{{ artifact.run_id }}</dd>
                <dt>Case</dt>
                <dd>{{ artifact.case_id ?? '未关联' }}</dd>
                <dt>Step</dt>
                <dd>{{ artifact.step_id ?? '未关联' }}</dd>
                <dt>Artifact</dt>
                <dd>{{ artifact.artifact_id }}</dd>
              </dl>
            </article>
          </div>
        </section>
        <dialog
          ref="screenshotDialog"
          class="screenshot-dialog"
          aria-label="截图预览"
          @close="selectedScreenshot = null"
        >
          <div v-if="selectedScreenshot" class="panel-title">
            <h4>{{ selectedScreenshot.artifact_id }}</h4>
            <button
              class="text-button"
              type="button"
              @click="screenshotDialog?.close()"
            >
              关闭
            </button>
          </div>
          <img
            v-if="
              selectedScreenshot &&
              !unavailableScreenshots.has(selectedScreenshot.artifact_id)
            "
            :src="artifactUrl(selectedScreenshot.artifact_id)"
            alt="放大的测试证据截图"
            @error="markUnavailable(selectedScreenshot.artifact_id)"
          />
          <p v-else-if="selectedScreenshot" class="empty-copy">
            截图暂不可用。
          </p>
        </dialog>
      </section>

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
