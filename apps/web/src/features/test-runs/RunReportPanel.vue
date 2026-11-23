<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import {
  getArtifact,
  getRunReport,
  isApiError,
  type ArtifactView,
  type RunReport,
} from '../../api';
import StateBadge from '../../components/StateBadge.vue';
import { verdictLabels } from './presentation';

const props = defineProps<{ runId: string; available: boolean }>();
const report = ref<RunReport | null>(null);
const loading = ref(false);
const errorCode = ref('');
const errorMessage = ref('');
const artifactError = ref('');
const artifactPreview = ref('');
const artifactPreviewTitle = ref('');
let controller: AbortController | null = null;
let objectUrl = '';

const artifactById = computed(
  () =>
    new Map(
      report.value?.artifacts.map((artifact) => [
        artifact.artifact_id,
        artifact,
      ]) ?? [],
    ),
);

function displayValue(value: unknown): string {
  if (value === null) return 'null';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

async function load(): Promise<void> {
  if (!props.available || loading.value) return;
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  errorCode.value = '';
  errorMessage.value = '';
  try {
    report.value = await getRunReport(props.runId, controller.signal);
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return;
    errorMessage.value =
      error instanceof Error ? error.message : '读取报告失败';
    errorCode.value = isApiError(error) ? error.code : 'UNKNOWN_ERROR';
  } finally {
    loading.value = false;
  }
}

async function openArtifact(artifact: ArtifactView): Promise<void> {
  artifactError.value = '';
  artifactPreview.value = '';
  artifactPreviewTitle.value = artifact.artifact_id;
  if (objectUrl) window.URL.revokeObjectURL(objectUrl);
  objectUrl = '';
  try {
    const response = await getArtifact(artifact.artifact_id);
    const blob = await response.blob();
    if (artifact.mime_type === 'application/json') {
      artifactPreview.value = JSON.stringify(
        JSON.parse(await blob.text()),
        null,
        2,
      );
      return;
    }
    objectUrl = window.URL.createObjectURL(blob);
    if (artifact.mime_type === 'image/png') {
      artifactPreview.value = objectUrl;
      return;
    }
    const anchor = window.document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = `${artifact.artifact_id}.zip`;
    anchor.click();
  } catch (error) {
    const code = isApiError(error) ? error.code : 'ARTIFACT_READ_FAILED';
    artifactError.value = `${code}：${error instanceof Error ? error.message : '证据读取失败'}`;
  }
}

function openEvidence(evidenceId: string): void {
  const artifact = artifactById.value.get(evidenceId);
  if (artifact) void openArtifact(artifact);
}

watch(
  () => [props.runId, props.available] as const,
  ([, available]) => {
    report.value = null;
    if (available) void load();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  controller?.abort();
  if (objectUrl) window.URL.revokeObjectURL(objectUrl);
});
</script>

<template>
  <div class="panel detail-panel report-panel">
    <div class="panel-title">
      <div>
        <h2>报告与证据</h2>
        <p>结构化结果来自 C1，证据通过 C5 同源授权地址读取。</p>
      </div>
      <span class="feature-label">C5</span>
    </div>

    <div v-if="!available" class="report-state">
      <span>◌</span>
      <div>
        <strong>报告尚未就绪</strong>
        <p>任务进入终态后可以查询报告。</p>
      </div>
    </div>
    <div v-else-if="loading" class="loading-state report-loading">
      <span class="spinner spinner-dark"></span>正在加载结构化报告…
    </div>
    <div
      v-else-if="errorMessage"
      class="report-state report-error"
      role="alert"
    >
      <span>!</span>
      <div>
        <strong>{{ errorCode }}</strong>
        <p>{{ errorMessage }}</p>
        <button class="text-button" type="button" @click="load">
          重新查询
        </button>
      </div>
    </div>

    <template v-else-if="report">
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

      <article
        v-for="testCase in report.cases"
        :key="testCase.case_id"
        class="report-case"
      >
        <header>
          <div>
            <small>{{ testCase.case_id }}</small>
            <h3>{{ testCase.name }}</h3>
          </div>
          <StateBadge
            v-if="testCase.verdict"
            :tone="testCase.verdict"
            :label="verdictLabels[testCase.verdict]"
          />
          <span v-else>未判定</span>
        </header>
        <p>{{ testCase.expected_behavior }}</p>
        <details open>
          <summary>执行步骤（{{ testCase.steps.length }}）</summary>
          <div
            v-for="step in testCase.steps"
            :key="step.step_id"
            class="report-step"
          >
            <strong>{{ step.summary ?? '执行步骤' }}</strong
            ><small>{{ step.step_id }}</small>
            <ul>
              <li v-for="call in step.tool_calls" :key="call.tool_call_id">
                <code>{{ call.tool }}</code
                ><span
                  :class="
                    call.success === null
                      ? 'text-inconclusive'
                      : call.success
                        ? 'text-passed'
                        : 'text-failed'
                  "
                  >{{
                    call.success === null
                      ? '未完成'
                      : call.success
                        ? '成功'
                        : '失败'
                  }}</span
                ><span v-if="call.duration_ms !== null"
                  >{{ call.duration_ms }} ms</span
                >
              </li>
            </ul>
          </div>
        </details>
        <details open>
          <summary>断言复核（{{ testCase.assertions.length }}）</summary>
          <div
            v-for="assertion in testCase.assertions"
            :key="assertion.assertion_id"
            class="assertion-row"
          >
            <div>
              <strong>{{ assertion.assertion_id }}</strong
              ><span
                :class="
                  assertion.passed === true
                    ? 'text-passed'
                    : assertion.passed === false
                      ? 'text-failed'
                      : 'text-inconclusive'
                "
                >{{
                  assertion.passed === null
                    ? '未判定'
                    : assertion.passed
                      ? '通过'
                      : '失败'
                }}</span
              >
            </div>
            <dl>
              <dt>预期</dt>
              <dd>{{ displayValue(assertion.expected) }}</dd>
              <dt>实际</dt>
              <dd>{{ displayValue(assertion.actual) }}</dd>
            </dl>
            <div class="evidence-links">
              <button
                v-for="evidenceId in assertion.evidence_ids"
                :key="evidenceId"
                class="text-button"
                type="button"
                :disabled="!artifactById.get(evidenceId)"
                @click="openEvidence(evidenceId)"
              >
                查看证据 {{ evidenceId }}
              </button>
            </div>
          </div>
        </details>
      </article>

      <div v-if="report.artifacts.length" class="artifact-list">
        <h3>全部证据</h3>
        <button
          v-for="artifact in report.artifacts"
          :key="artifact.artifact_id"
          type="button"
          @click="openArtifact(artifact)"
        >
          <span>{{ artifact.kind }}</span
          ><strong>{{ artifact.artifact_id }}</strong
          ><small>{{ artifact.mime_type }} · {{ artifact.size_bytes }} B</small>
        </button>
      </div>
      <div v-if="artifactError" class="alert alert-error" role="alert">
        <strong>{{ artifactError }}</strong>
      </div>
      <div v-if="artifactPreview" class="artifact-preview">
        <div class="panel-title">
          <h3>{{ artifactPreviewTitle }}</h3>
          <button
            class="text-button"
            type="button"
            @click="artifactPreview = ''"
          >
            关闭
          </button>
        </div>
        <img
          v-if="artifactPreview.startsWith('blob:')"
          :src="artifactPreview"
          alt="测试证据截图"
        />
        <pre v-else>{{ artifactPreview }}</pre>
      </div>
    </template>
  </div>
</template>
