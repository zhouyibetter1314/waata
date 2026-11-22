<script setup lang="ts">
withDefaults(
  defineProps<{
    value: number;
    label?: string;
  }>(),
  { label: '任务进度' },
);
</script>

<template>
  <div
    class="progress-track"
    role="progressbar"
    :aria-label="label"
    aria-valuemin="0"
    aria-valuemax="100"
    :aria-valuenow="value"
  >
    <span :style="{ width: `${value}%` }"></span>
  </div>
</template>
