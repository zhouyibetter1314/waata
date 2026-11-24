import { defineStore } from 'pinia';

export interface CatalogApplication {
  id: string;
  name: string;
  base_url: string;
  credential_ref: string | null;
  version: string;
}

export interface CatalogScenario {
  id: string;
  application_id: string;
  name: string;
  goal: string;
  expected_behavior: string;
  source: string;
}

interface CatalogState {
  applications: CatalogApplication[];
  scenarios: CatalogScenario[];
  maxSteps: number;
}

const STORAGE_KEY = 'waata.frontend.catalog.v1';

const retiredDefaultScenario: CatalogScenario = {
  id: 'scenario_create_project',
  application_id: 'app_4gaboards',
  name: '创建项目并验证两个位置',
  goal: '在本地 4gaBoards 创建名为 Course Test 01 的项目。',
  expected_behavior: '创建完成后，仪表盘和侧边栏均显示 Course Test 01。',
  source: 'C1 正式样例',
};

const defaults: CatalogState = {
  applications: [
    {
      id: 'app_4gaboards',
      name: '4gaBoards',
      base_url: 'http://localhost:3000/',
      credential_ref: 'boards_local_fixture',
      version: '3.2.16',
    },
  ],
  scenarios: [],
  maxSteps: 12,
};

function cloneDefaults(): CatalogState {
  return structuredClone(defaults);
}

function initialState(): CatalogState {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (!value) return cloneDefaults();
    const parsed = JSON.parse(value) as Partial<CatalogState>;
    if (!Array.isArray(parsed.applications) || !Array.isArray(parsed.scenarios))
      return cloneDefaults();
    const scenarios = parsed.scenarios.filter(
      (scenario) =>
        !Object.entries(retiredDefaultScenario).every(
          ([key, field]) => scenario?.[key as keyof CatalogScenario] === field,
        ),
    );
    if (scenarios.length !== parsed.scenarios.length) {
      try {
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({ ...parsed, scenarios }),
        );
      } catch {
        // The remaining scenarios can still be loaded if storage is full.
      }
    }
    return {
      applications: parsed.applications,
      scenarios,
      maxSteps:
        Number.isInteger(parsed.maxSteps) && Number(parsed.maxSteps) > 0
          ? Number(parsed.maxSteps)
          : 12,
    };
  } catch {
    return cloneDefaults();
  }
}

function newId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export const useCatalogStore = defineStore('catalog', {
  state: initialState,
  actions: {
    persist(): void {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          applications: this.applications,
          scenarios: this.scenarios,
          maxSteps: this.maxSteps,
        }),
      );
    },
    saveApplication(
      value: Omit<CatalogApplication, 'id'> & { id?: string },
    ): string {
      const id = value.id || newId('app');
      const next: CatalogApplication = { ...value, id };
      const index = this.applications.findIndex((item) => item.id === id);
      if (index >= 0) this.applications[index] = next;
      else this.applications.push(next);
      this.persist();
      return id;
    },
    removeApplication(id: string): void {
      this.applications = this.applications.filter((item) => item.id !== id);
      this.scenarios = this.scenarios.filter(
        (item) => item.application_id !== id,
      );
      this.persist();
    },
    saveScenario(value: Omit<CatalogScenario, 'id'> & { id?: string }): string {
      const id = value.id || newId('scenario');
      const next: CatalogScenario = { ...value, id };
      const index = this.scenarios.findIndex((item) => item.id === id);
      if (index >= 0) this.scenarios[index] = next;
      else this.scenarios.push(next);
      this.persist();
      return id;
    },
    removeScenario(id: string): void {
      this.scenarios = this.scenarios.filter((item) => item.id !== id);
      this.persist();
    },
    setMaxSteps(value: number): void {
      this.maxSteps = value;
      this.persist();
    },
    importScenarios(
      values: Array<Omit<CatalogScenario, 'id'> & { id?: string }>,
    ): number {
      for (const value of values) this.saveScenario(value);
      return values.length;
    },
  },
});
