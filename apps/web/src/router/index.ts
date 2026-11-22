import { createRouter, createWebHistory } from 'vue-router';
import ScenarioWorkspaceView from '../features/catalog/ScenarioWorkspaceView.vue';
import SettingsView from '../features/settings/SettingsView.vue';
import CreateRunView from '../features/test-runs/CreateRunView.vue';
import RunDetailView from '../features/test-runs/RunDetailView.vue';
import RunListView from '../features/test-runs/RunListView.vue';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/scenarios' },
    {
      path: '/scenarios',
      name: 'scenario-workspace',
      component: ScenarioWorkspaceView,
      meta: { title: '场景与应用' },
    },
    {
      path: '/runs',
      name: 'run-list',
      component: RunListView,
      meta: { title: '运行与报告' },
    },
    {
      path: '/runs/new',
      name: 'run-create',
      component: CreateRunView,
      meta: { title: '创建测试' },
    },
    {
      path: '/runs/:runId',
      name: 'run-detail',
      component: RunDetailView,
      meta: { title: '运行详情' },
    },
    { path: '/reviews', redirect: '/runs' },
    {
      path: '/settings',
      name: 'settings',
      component: SettingsView,
      meta: { title: '环境与设置' },
    },
  ],
});
