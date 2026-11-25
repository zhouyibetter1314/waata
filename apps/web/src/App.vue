<script setup lang="ts">
import { useRoute } from 'vue-router';

const route = useRoute();
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/scenarios" aria-label="WAATA 首页">
        <span class="brand-mark">W<span> / </span>A</span>
      </RouterLink>
      <div class="brand-copy">
        <strong>自主测试工作台</strong>
        <small>Web App Auto Test Agent</small>
      </div>

      <nav class="primary-nav" aria-label="主导航">
        <RouterLink to="/scenarios">
          <span class="nav-icon" aria-hidden="true">◇</span>
          <span
            ><strong>场景与应用</strong
            ><small>配置、导入与批量运行</small></span
          >
        </RouterLink>
        <RouterLink to="/runs" aria-label="测试任务">
          <span class="nav-icon" aria-hidden="true">▦</span>
          <span><strong>运行与报告</strong><small>任务状态与结果</small></span>
        </RouterLink>
        <RouterLink to="/settings">
          <span class="nav-icon" aria-hidden="true">⚙</span>
          <span
            ><strong>环境与设置</strong
            ><small>接口、契约与运行配置</small></span
          >
        </RouterLink>
      </nav>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <div>
          <span class="breadcrumb">WAATA /</span>
          <strong>{{ route.meta.title ?? '测试工作台' }}</strong>
        </div>
      </header>
      <RouterView />
    </main>
  </div>
</template>
