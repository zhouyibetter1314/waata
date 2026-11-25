import { afterAll, afterEach, beforeAll } from 'vitest';
import { server } from './fixtures/server';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
  document.body.innerHTML = '';
});
afterAll(() => server.close());
