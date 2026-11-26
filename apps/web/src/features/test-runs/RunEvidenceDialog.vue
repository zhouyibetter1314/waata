<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { artifactUrl, getArtifact } from '../../api';
import { formatError } from './presentation';

const dialog = ref<HTMLDialogElement | null>(null);
const heading = ref('');
const ids = ref<string[]>([]);
const index = ref(0);
const selected = computed(() => ids.value[index.value]);
const loading = ref(false);
const error = ref('');
const image = ref('');
const data = ref<Record<string, unknown> | null>(null);
const download = ref('');

function open(title: string, evidenceIds: string[]): void {
  if (!evidenceIds.length) return;
  heading.value = title;
  index.value = 0;
  ids.value = evidenceIds;
  if (!dialog.value?.open) dialog.value?.showModal();
}

defineExpose({ open });

watch(selected, async (id, _, onCleanup) => {
  const controller = new AbortController();
  let objectUrl = '';
  onCleanup(() => {
    controller.abort();
    if (objectUrl) window.URL.revokeObjectURL(objectUrl);
  });

  image.value = '';
  data.value = null;
  error.value = '';
  download.value = '';
  loading.value = Boolean(id);
  if (!id) return;

  try {
    const response = await getArtifact(id, controller.signal);
    const type = response.headers.get('Content-Type')?.split(';')[0];
    if (type === 'application/json') {
      const value = await response.json();
      if (!controller.signal.aborted) data.value = value;
    } else if (type === 'image/png') {
      const blob = await response.blob();
      if (!controller.signal.aborted) {
        objectUrl = window.URL.createObjectURL(blob);
        image.value = objectUrl;
      }
    }
    if (!controller.signal.aborted) {
      download.value =
        type === 'image/png'
          ? `${id}.png`
          : type === 'application/json'
            ? `${id}.json`
            : `${id}.zip`;
    }
  } catch (cause) {
    if (!controller.signal.aborted) error.value = formatError(cause);
  } finally {
    if (!controller.signal.aborted) loading.value = false;
  }
});

function display(value: unknown): string {
  if (value === true) return '是';
  if (value === false) return '否';
  return typeof value === 'string' ? value : (JSON.stringify(value) ?? '—');
}
</script>

<template>
  <dialog
    ref="dialog"
    class="screenshot-dialog evidence-dialog"
    aria-labelledby="run-evidence-title"
    @close="ids = []"
  >
    <div class="panel-title">
      <div>
        <h3 id="run-evidence-title">测试证据</h3>
        <p>{{ heading }}</p>
      </div>
      <form method="dialog">
        <button class="button button-secondary">关闭</button>
      </form>
    </div>
    <label v-if="ids.length > 1" class="evidence-selector">
      选择证据
      <select v-model="index">
        <option v-for="(id, position) in ids" :key="id" :value="position">
          第 {{ position + 1 }} 项
        </option>
      </select>
    </label>
    <p v-if="loading" role="status">正在读取证据…</p>
    <p v-else-if="error" role="alert">{{ error }}</p>
    <template v-else>
      <img
        v-if="image"
        :src="image"
        alt="本次操作的页面截图"
        @error="error = '截图无法显示。'"
      />
      <template v-else-if="data">
        <dl class="detail-list">
          <template v-if="data.title">
            <dt>页面标题</dt>
            <dd>{{ data.title }}</dd>
          </template>
          <template v-if="data.url">
            <dt>页面地址</dt>
            <dd>{{ data.url }}</dd>
          </template>
          <template v-if="data.matched !== undefined">
            <dt>符合预期</dt>
            <dd>{{ display(data.matched) }}</dd>
          </template>
          <template v-if="data.expected !== undefined">
            <dt>预期值</dt>
            <dd>{{ display(data.expected) }}</dd>
          </template>
          <template v-if="data.actual !== undefined">
            <dt>实际值</dt>
            <dd>{{ display(data.actual) }}</dd>
          </template>
        </dl>
        <details v-if="data.aria">
          <summary>查看页面文字与控件</summary>
          <pre>{{ data.aria }}</pre>
        </details>
        <details>
          <summary>查看原始记录</summary>
          <pre>{{ JSON.stringify(data, null, 2) }}</pre>
        </details>
      </template>
      <p v-else-if="download">此证据可下载查看。</p>
      <a
        v-if="selected && download"
        :href="artifactUrl(selected)"
        :download="download"
        class="text-button"
        >下载证据</a
      >
    </template>
  </dialog>
</template>
