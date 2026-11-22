<script setup lang="ts">
defineProps<{ tone: string; label: string }>();
</script>

<template>
  <span class="badge" :class="`badge-${tone}`">
    <span class="badge-dot" aria-hidden="true"></span>{{ label }}
  </span>
</template>
