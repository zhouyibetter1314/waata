import { createPinia } from 'pinia';
import { createApp } from 'vue';
import App from './App.vue';
import { router } from './router';
import './style.css';

async function enableMocking(): Promise<void> {
  if (!import.meta.env.DEV || import.meta.env.VITE_API_MOCKING === 'disabled')
    return;
  const { worker } = await import('./mocks/browser');
  await worker.start({ onUnhandledRequest: 'bypass' });
}

await enableMocking();
createApp(App).use(createPinia()).use(router).mount('#app');
