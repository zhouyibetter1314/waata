<script setup lang="ts">
import { computed, ref } from 'vue';
import type { PublishedEvent } from '../../api';
import RunEvidenceDialog from './RunEvidenceDialog.vue';
import RunReportPanel from './RunReportPanel.vue';
import {
  evidenceIds,
  eventSummary,
  eventTone,
  screenshotIds,
  summarizeTimeline,
  timelineTitle,
} from './events';
import { formatDate } from './presentation';

const props = defineProps<{
  events: PublishedEvent[];
  connectionMessage: string;
  runId?: string;
  reportAvailable?: boolean;
}>();
const evidenceDialog = ref<InstanceType<typeof RunEvidenceDialog> | null>(null);
const showAll = ref(false);
const entries = computed(() =>
  showAll.value
    ? props.events.map((event) => ({ event, count: 1, followUp: undefined }))
    : summarizeTimeline(props.events),
);
</script>

<template>
  <div class="panel detail-panel timeline-panel">
    <div class="panel-title">
      <div>
        <h2>执行时间线</h2>
        <p>{{ connectionMessage || '等待连接事件流' }}</p>
      </div>
      <button
        v-if="events.length"
        type="button"
        class="text-button"
        :aria-expanded="showAll"
        aria-controls="run-event-list"
        @click="showAll = !showAll"
      >
        {{ showAll ? '返回摘要' : `查看全部事件（${events.length}）` }}
      </button>
    </div>
    <RunReportPanel
      v-if="runId"
      :run-id="runId"
      :available="Boolean(reportAvailable)"
      :events="events"
      @evidence="(title, ids) => evidenceDialog?.open(title, ids)"
    />
    <div v-if="!events.length" class="timeline-empty">
      <span class="spinner spinner-dark"></span>
      <p>{{ reportAvailable ? '暂无执行事件。' : '等待第一条运行事件…' }}</p>
    </div>
    <ol v-else id="run-event-list" class="event-timeline">
      <li
        v-for="{ event, count, followUp } in entries"
        :key="`${event.run_id}:${event.sequence}`"
        :class="`event-${eventTone(event)}`"
      >
        <span class="event-index" :aria-hidden="!showAll">
          {{ showAll ? event.sequence : '•' }}
        </span>
        <div>
          <div class="event-heading">
            <strong>{{ timelineTitle(event) }}</strong>
            <time>{{ formatDate(event.timestamp) }}</time>
          </div>
          <p>{{ eventSummary(event) }}</p>
          <p v-if="followUp">{{ followUp }}</p>
          <small
            v-if="
              event.type === 'tool.completed' && event.payload.success === false
            "
            ><code>{{ event.payload.error_code }}</code
            ><template v-if="count > 1"> · {{ count }} 次</template></small
          >
          <button
            v-if="evidenceIds(event).length"
            type="button"
            class="text-button"
            @click="
              evidenceDialog?.open(timelineTitle(event), evidenceIds(event))
            "
          >
            {{
              screenshotIds(event).length === 1 &&
              evidenceIds(event).length === 1
                ? '查看本步截图'
                : `查看证据（${evidenceIds(event).length}）`
            }}
          </button>
          <small v-if="showAll && event.case_id"
            >{{ event.case_id
            }}<template v-if="event.step_id">
              / {{ event.step_id }}</template
            ></small
          >
          <details v-if="showAll">
            <summary>查看事件数据</summary>
            <pre>{{ JSON.stringify(event.payload, null, 2) }}</pre>
          </details>
        </div>
      </li>
    </ol>
    <RunEvidenceDialog ref="evidenceDialog" />
  </div>
</template>
