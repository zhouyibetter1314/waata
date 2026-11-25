<script setup lang="ts">
import type { PublishedEvent } from '../../api';
import { eventLabels, eventSummary, eventTone } from './events';
import { formatDate } from './presentation';

function screenshotIds(event: PublishedEvent): string[] {
  if (event.type !== 'tool.completed' || event.payload.tool !== 'browser.screenshot') return [];
  const ids = event.payload.evidence_ids;
  return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string') : [];
}

defineProps<{
  events: PublishedEvent[];
  connectionMessage: string;
  cursor: number;
}>();
</script>

<template>
  <div class="panel detail-panel timeline-panel">
    <div class="panel-title">
      <div>
        <h2>执行时间线</h2>
        <p>{{ connectionMessage || '等待连接事件流' }}</p>
      </div>
      <span class="feature-label">C4 · #{{ cursor }}</span>
    </div>
    <div v-if="!events.length" class="timeline-empty">
      <span class="spinner spinner-dark"></span>
      <p>等待第一条运行事件…</p>
    </div>
    <ol v-else class="event-timeline">
      <li
        v-for="event in events"
        :key="`${event.run_id}:${event.sequence}`"
        :class="`event-${eventTone(event)}`"
      >
        <span class="event-index">{{ event.sequence }}</span>
        <div>
          <div class="event-heading">
            <strong>{{ eventLabels[event.type] ?? event.type }}</strong
            ><time>{{ formatDate(event.timestamp) }}</time>
          </div>
          <p>{{ eventSummary(event) }}</p>
          <a
            v-for="id in screenshotIds(event)"
            :key="id"
            class="text-button"
            :href="'/api/v1/artifacts/' + encodeURIComponent(id)"
            target="_blank"
            rel="noopener noreferrer"
          >查看本步截图</a>
          <small v-if="event.case_id"
            >{{ event.case_id
            }}<template v-if="event.step_id">
              / {{ event.step_id }}</template
            ></small
          >
          <details>
            <summary>查看事件数据</summary>
            <pre>{{ JSON.stringify(event.payload, null, 2) }}</pre>
          </details>
        </div>
      </li>
    </ol>
  </div>
</template>
