<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string;
    description: string;
    icon?: string;
  }>(),
  { icon: '◇' },
);
</script>

<template>
  <div class="empty-state">
    <span class="empty-icon" aria-hidden="true">{{ icon }}</span>
    <h2>{{ title }}</h2>
    <p>{{ description }}</p>
    <slot />
  </div>
</template>
