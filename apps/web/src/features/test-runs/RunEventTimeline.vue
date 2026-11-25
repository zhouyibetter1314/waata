<script setup lang="ts">
import { computed, ref } from 'vue';
import type { PublishedEvent } from '../../api';
import {
  eventLabels,
  eventSummary,
  eventTone,
  summarizeTimeline,
} from './events';
import { formatDate } from './presentation';

function screenshotIds(event: PublishedEvent): string[] {
  if (
    event.type !== 'tool.completed' ||
    event.payload.tool !== 'browser.screenshot'
  )
    return [];
  const ids = event.payload.evidence_ids;
  return Array.isArray(ids)
    ? ids.filter((id): id is string => typeof id === 'string')
    : [];
}

const props = defineProps<{
  events: PublishedEvent[];
  connectionMessage: string;
}>();
const showAll = ref(false);
const entries = computed(() =>
  showAll.value
    ? props.events.map((event) => ({ event, count: 1 }))
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
    <div v-if="!events.length" class="timeline-empty">
      <span class="spinner spinner-dark"></span>
      <p>等待第一条运行事件…</p>
    </div>
    <ol v-else id="run-event-list" class="event-timeline">
      <li
        v-for="{ event, count } in entries"
        :key="`${event.run_id}:${event.sequence}`"
        :class="`event-${eventTone(event)}`"
      >
        <span class="event-index" :aria-hidden="!showAll">
          {{ showAll ? event.sequence : '•' }}
        </span>
        <div>
          <div class="event-heading">
            <strong>{{
              !showAll && event.type === 'tool.completed'
                ? event.payload.success === false
                  ? '工具失败'
                  : '已保存截图'
                : (eventLabels[event.type] ?? event.type)
            }}</strong
            ><time>{{ formatDate(event.timestamp) }}</time>
          </div>
          <p>
            {{ eventSummary(event)
            }}<template v-if="count > 1"> · {{ count }} 次</template>
          </p>
          <a
            v-for="id in screenshotIds(event)"
            :key="id"
            class="text-button"
            :href="'/api/v1/artifacts/' + encodeURIComponent(id)"
            target="_blank"
            rel="noopener noreferrer"
            >查看本步截图</a
          >
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
  </div>
</template>
