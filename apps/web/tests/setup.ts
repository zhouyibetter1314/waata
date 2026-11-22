import { afterAll, afterEach, beforeAll } from 'vitest';
import { resetMockData } from '../src/mocks/handlers';
import { server } from '../src/mocks/server';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  resetMockData();
  localStorage.clear();
  document.body.innerHTML = '';
});
afterAll(() => server.close());
