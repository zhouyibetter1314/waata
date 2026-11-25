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

const retiredDefaultApplication: CatalogApplication = {
  id: 'app_4gaboards',
  name: '4gaBoards',
  base_url: 'http://localhost:3000/',
  credential_ref: 'boards_local_fixture',
  version: '3.2.16',
};

const retiredDefaultScenario: CatalogScenario = {
  id: 'scenario_create_project',
  application_id: 'app_4gaboards',
  name: '创建项目并验证两个位置',
  goal: '在本地 4gaBoards 创建名为 Course Test 01 的项目。',
  expected_behavior: '创建完成后，仪表盘和侧边栏均显示 Course Test 01。',
  source: 'C1 正式样例',
};

function emptyCatalog(): CatalogState {
  return { applications: [], scenarios: [], maxSteps: 12 };
}

function initialState(): CatalogState {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (!value) return emptyCatalog();
    const parsed = JSON.parse(value) as Partial<CatalogState>;
    if (!Array.isArray(parsed.applications) || !Array.isArray(parsed.scenarios))
      return emptyCatalog();
    const scenarios = parsed.scenarios.filter(
      (scenario) =>
        !Object.entries(retiredDefaultScenario).every(
          ([key, field]) => scenario?.[key as keyof CatalogScenario] === field,
        ),
    );
    const applications = parsed.applications.filter(
      (application) =>
        scenarios.some(
          (scenario) => scenario?.application_id === application?.id,
        ) ||
        !Object.entries(retiredDefaultApplication).every(
          ([key, field]) =>
            application?.[key as keyof CatalogApplication] === field,
        ),
    );
    if (
      scenarios.length !== parsed.scenarios.length ||
      applications.length !== parsed.applications.length
    ) {
      try {
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({ ...parsed, applications, scenarios }),
        );
      } catch {
        // A storage write failure does not prevent loading the saved catalog.
      }
    }
    return {
      applications,
      scenarios,
      maxSteps:
        Number.isInteger(parsed.maxSteps) && Number(parsed.maxSteps) > 0
          ? Number(parsed.maxSteps)
          : 12,
    };
  } catch {
    return emptyCatalog();
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
