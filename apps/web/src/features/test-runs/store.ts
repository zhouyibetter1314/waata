import { defineStore } from 'pinia';
import { listRuns, type RunSummary } from '../../api';
import { formatError } from './presentation';

let requestSequence = 0;

export const useTestRunsStore = defineStore('test-runs', {
  state: () => ({
    items: [] as RunSummary[],
    page: 1,
    pageSize: 20,
    total: 0,
    loading: false,
    error: '',
  }),
  actions: {
    async load(page?: number): Promise<void> {
      const targetPage = page ?? this.page;
      const current = ++requestSequence;
      this.loading = true;
      this.error = '';
      try {
        const result = await listRuns({
          page: targetPage,
          pageSize: this.pageSize,
        });
        if (current !== requestSequence) return;
        this.items = result.items;
        this.page = result.page;
        this.pageSize = result.page_size;
        this.total = result.total;
      } catch (error) {
        if (current === requestSequence) this.error = formatError(error);
      } finally {
        if (current === requestSequence) this.loading = false;
      }
    },
  },
});
