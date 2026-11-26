<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { createRun } from '../../api';
import {
  useCatalogStore,
  type CatalogApplication,
  type CatalogScenario,
} from './store';

const catalog = useCatalogStore();
const router = useRouter();
const busy = ref(false);
const error = ref('');
const notice = ref('');
const selected = ref<string[]>([]);
const applicationDialog = ref(false);
const scenarioDialog = ref(false);
const importDialog = ref(false);
const importedJson = ref('');

const applicationForm = reactive({
  id: '',
  name: '',
  base_url: '',
  credential_ref: '',
  version: '',
});
const scenarioForm = reactive({
  id: '',
  application_id: '',
  name: '',
  goal: '',
  expected_behavior: '',
  source: '自建场景',
});

const selectedCount = computed(() => selected.value.length);

function applicationName(id: string): string {
  return (
    catalog.applications.find((item) => item.id === id)?.name ?? '应用已删除'
  );
}

function validateUrl(value: string): string {
  try {
    const url = new window.URL(value);
    if (!['http:', 'https:'].includes(url.protocol))
      return '应用地址必须使用 HTTP(S)';
    if (url.username || url.password) return '应用地址不能包含用户名或密码';
    return '';
  } catch {
    return '请输入有效的绝对 HTTP(S) 地址';
  }
}

function openApplication(value?: CatalogApplication): void {
  Object.assign(applicationForm, {
    id: value?.id ?? '',
    name: value?.name ?? '',
    base_url: value?.base_url ?? '',
    credential_ref: value?.credential_ref ?? '',
    version: value?.version ?? '',
  });
  error.value = '';
  applicationDialog.value = true;
}

function saveApplication(): void {
  error.value = '';
  if (!applicationForm.name.trim()) {
    error.value = '请输入应用名称';
    return;
  }
  const urlError = validateUrl(applicationForm.base_url.trim());
  if (urlError) {
    error.value = urlError;
    return;
  }
  catalog.saveApplication({
    id: applicationForm.id || undefined,
    name: applicationForm.name.trim(),
    base_url: applicationForm.base_url.trim(),
    credential_ref: applicationForm.credential_ref.trim() || null,
    version: applicationForm.version.trim(),
  });
  applicationDialog.value = false;
  notice.value = '应用配置已保存在当前浏览器';
}

function removeApplication(id: string): void {
  catalog.removeApplication(id);
  selected.value = selected.value.filter((scenarioId) =>
    catalog.scenarios.some((scenario) => scenario.id === scenarioId),
  );
  notice.value = '应用及其关联场景已从本地场景库删除';
}

function openScenario(value?: CatalogScenario): void {
  if (!catalog.applications.length) {
    error.value = '请先添加一个被测应用';
    return;
  }
  Object.assign(scenarioForm, {
    id: value?.id ?? '',
    application_id: value?.application_id ?? catalog.applications[0]?.id ?? '',
    name: value?.name ?? '',
    goal: value?.goal ?? '',
    expected_behavior: value?.expected_behavior ?? '',
    source: value?.source ?? '自建场景',
  });
  error.value = '';
  scenarioDialog.value = true;
}

function saveScenario(): void {
  error.value = '';
  if (
    !scenarioForm.application_id ||
    !catalog.applications.some(
      (item) => item.id === scenarioForm.application_id,
    )
  ) {
    error.value = '请选择有效的被测应用';
    return;
  }
  if (
    !scenarioForm.name.trim() ||
    !scenarioForm.goal.trim() ||
    !scenarioForm.expected_behavior.trim()
  ) {
    error.value = '场景名称、测试目标和预期行为均不能为空';
    return;
  }
  catalog.saveScenario({
    id: scenarioForm.id || undefined,
    application_id: scenarioForm.application_id,
    name: scenarioForm.name.trim(),
    goal: scenarioForm.goal.trim(),
    expected_behavior: scenarioForm.expected_behavior.trim(),
    source: scenarioForm.source.trim() || '自建场景',
  });
  scenarioDialog.value = false;
  notice.value = '测试场景已保存';
}

function removeScenario(id: string): void {
  catalog.removeScenario(id);
  selected.value = selected.value.filter((item) => item !== id);
  notice.value = '测试场景已删除';
}

function setSelected(id: string, checked: boolean): void {
  selected.value = checked
    ? [...new Set([...selected.value, id])]
    : selected.value.filter((item) => item !== id);
}

async function launch(ids: string[]): Promise<void> {
  if (!ids.length || busy.value) return;
  busy.value = true;
  error.value = '';
  notice.value = '';
  try {
    let lastRunId = '';
    for (const id of ids) {
      const scenario = catalog.scenarios.find((item) => item.id === id);
      const application = catalog.applications.find(
        (item) => item.id === scenario?.application_id,
      );
      if (!scenario || !application) throw new Error('场景关联的应用不存在');
      const created = await createRun({
        target_url: application.base_url,
        goal: scenario.goal,
        expected_behavior: scenario.expected_behavior,
        credential_ref: application.credential_ref,
        options: { headless: true, max_steps_per_case: catalog.maxSteps },
      });
      lastRunId = created.run_id;
    }
    selected.value = [];
    if (ids.length === 1)
      await router.push(`/runs/${encodeURIComponent(lastRunId)}`);
    else await router.push('/runs');
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '运行场景失败';
  } finally {
    busy.value = false;
  }
}

function importScenarios(): void {
  error.value = '';
  try {
    const values = JSON.parse(importedJson.value) as unknown;
    if (!Array.isArray(values) || !values.length)
      throw new Error('请输入非空场景数组');
    const scenarios = values.map((item) => {
      if (!item || typeof item !== 'object')
        throw new Error('场景项必须是对象');
      const value = item as Record<string, unknown>;
      const applicationId = String(value.application_id ?? '');
      const name = String(value.name ?? '');
      const goal = String(value.goal ?? value.description ?? '');
      const expected = String(value.expected_behavior ?? '');
      if (
        !catalog.applications.some(
          (application) => application.id === applicationId,
        )
      )
        throw new Error(`场景 ${name || '未命名'} 引用了未知应用`);
      if (!name.trim() || !goal.trim() || !expected.trim())
        throw new Error('每个场景都必须包含 name、goal 和 expected_behavior');
      return {
        id: typeof value.id === 'string' ? value.id : undefined,
        application_id: applicationId,
        name: name.trim(),
        goal: goal.trim(),
        expected_behavior: expected.trim(),
        source: String(value.source ?? 'JSON 导入'),
      };
    });
    const count = catalog.importScenarios(scenarios);
    importedJson.value = '';
    importDialog.value = false;
    notice.value = `已导入 ${count} 个场景`;
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '场景 JSON 无法解析';
  }
}
</script>

<template>
  <section class="page">
    <div class="page-heading">
      <div>
        <div class="eyebrow">TEST DESIGN</div>
        <h1>场景与应用</h1>
        <p class="lead">
          在当前浏览器保存和复用测试场景，选中多个场景可以一次提交。
        </p>
      </div>
      <button
        class="button button-primary"
        type="button"
        :disabled="!catalog.applications.length"
        @click="openScenario()"
      >
        ＋ 新建场景
      </button>
    </div>

    <div v-if="error" class="alert alert-error" role="alert">
      <strong>{{ error }}</strong
      ><button class="text-button" type="button" @click="error = ''">
        关闭
      </button>
    </div>
    <div v-if="notice" class="alert alert-success">
      <strong>{{ notice }}</strong
      ><button class="text-button" type="button" @click="notice = ''">
        关闭
      </button>
    </div>

    <div class="catalog-summary">
      <div>
        <strong>{{ catalog.scenarios.length }}</strong
        ><span>测试场景</span>
      </div>
      <div>
        <strong>{{ catalog.applications.length }}</strong
        ><span>被测应用</span>
      </div>
      <label
        ><input
          :value="catalog.maxSteps"
          type="number"
          min="1"
          max="100"
          @change="
            catalog.setMaxSteps(
              Number(($event.target as HTMLInputElement).value),
            )
          "
        /><span>每用例 Agent 步骤上限</span></label
      >
    </div>

    <div class="panel catalog-panel">
      <div class="panel-toolbar">
        <div>
          <h2>应用配置</h2>
          <p>应用保存目标地址和测试凭据名称。</p>
        </div>
        <button
          class="button button-secondary"
          type="button"
          @click="openApplication()"
        >
          添加应用
        </button>
      </div>
      <div v-if="!catalog.applications.length" class="catalog-empty">
        请先添加被测应用，再创建测试场景。
      </div>
      <div
        v-for="application in catalog.applications"
        :key="application.id"
        class="application-row"
      >
        <div>
          <strong>{{ application.name }}</strong
          ><small>{{ application.base_url }}</small>
          <small>应用 ID {{ application.id }}</small>
        </div>
        <span class="catalog-chip">{{
          application.version || '版本未记录'
        }}</span>
        <span>{{ application.credential_ref || '无凭据引用' }}</span>
        <div>
          <button
            class="text-button"
            type="button"
            @click="openApplication(application)"
          >
            编辑</button
          ><button
            class="text-button text-danger"
            type="button"
            @click="removeApplication(application.id)"
          >
            删除
          </button>
        </div>
      </div>
    </div>

    <div class="panel catalog-panel">
      <div class="panel-toolbar">
        <div>
          <h2>场景库</h2>
          <p>选择一个或多个场景提交，每个场景会生成一条测试任务。</p>
        </div>
        <div class="toolbar-actions">
          <button
            class="button button-secondary"
            type="button"
            :disabled="!catalog.applications.length"
            @click="importDialog = true"
          >
            导入 JSON</button
          ><button
            class="button button-secondary"
            type="button"
            :disabled="!selectedCount || busy"
            @click="launch(selected)"
          >
            批量运行（{{ selectedCount }}）
          </button>
        </div>
      </div>
      <div v-if="!catalog.scenarios.length" class="catalog-empty">
        {{
          catalog.applications.length
            ? '还没有场景，点击“新建场景”开始。'
            : '还没有场景。'
        }}
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th></th>
              <th>场景</th>
              <th>测试目标</th>
              <th>被测应用</th>
              <th>来源</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="scenario in catalog.scenarios" :key="scenario.id">
              <td>
                <input
                  type="checkbox"
                  :checked="selected.includes(scenario.id)"
                  :aria-label="`选择 ${scenario.name}`"
                  @change="
                    setSelected(
                      scenario.id,
                      ($event.target as HTMLInputElement).checked,
                    )
                  "
                />
              </td>
              <td>
                <strong>{{ scenario.name }}</strong>
              </td>
              <td class="scenario-goal">{{ scenario.goal }}</td>
              <td>{{ applicationName(scenario.application_id) }}</td>
              <td>
                <span class="catalog-chip">{{ scenario.source }}</span>
              </td>
              <td class="catalog-actions">
                <button
                  class="text-button"
                  type="button"
                  @click="openScenario(scenario)"
                >
                  编辑</button
                ><button
                  class="text-button"
                  type="button"
                  :disabled="busy"
                  @click="launch([scenario.id])"
                >
                  运行</button
                ><button
                  class="text-button text-danger"
                  type="button"
                  @click="removeScenario(scenario.id)"
                >
                  删除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div
      v-if="applicationDialog"
      class="dialog-backdrop"
      @click.self="applicationDialog = false"
    >
      <form class="dialog" @submit.prevent="saveApplication">
        <div class="dialog-heading">
          <h2>{{ applicationForm.id ? '编辑被测应用' : '添加被测应用' }}</h2>
          <button type="button" @click="applicationDialog = false">×</button>
        </div>
        <label>应用名称 <b>*</b><input v-model="applicationForm.name" /></label
        ><label
          >应用地址 <b>*</b><input v-model="applicationForm.base_url" /></label
        ><label>版本<input v-model="applicationForm.version" /></label
        ><label
          >测试凭据名称<input v-model="applicationForm.credential_ref"
        /></label>
        <p>这里只填写服务端授权的引用名称，不输入真实凭据。</p>
        <div class="form-actions">
          <button
            class="button button-secondary"
            type="button"
            @click="applicationDialog = false"
          >
            取消</button
          ><button class="button button-primary" type="submit">保存应用</button>
        </div>
      </form>
    </div>

    <div
      v-if="scenarioDialog"
      class="dialog-backdrop"
      @click.self="scenarioDialog = false"
    >
      <form class="dialog dialog-wide" @submit.prevent="saveScenario">
        <div class="dialog-heading">
          <h2>{{ scenarioForm.id ? '编辑测试场景' : '新建测试场景' }}</h2>
          <button type="button" @click="scenarioDialog = false">×</button>
        </div>
        <label
          >被测应用 <b>*</b
          ><select v-model="scenarioForm.application_id">
            <option
              v-for="application in catalog.applications"
              :key="application.id"
              :value="application.id"
            >
              {{ application.name }}
            </option>
          </select></label
        ><label>场景名称 <b>*</b><input v-model="scenarioForm.name" /></label
        ><label
          >自然语言测试目标 <b>*</b
          ><textarea v-model="scenarioForm.goal" rows="4" /></label
        ><label
          >预期行为 <b>*</b
          ><textarea v-model="scenarioForm.expected_behavior" rows="4" /></label
        ><label>场景来源<input v-model="scenarioForm.source" /></label>
        <div class="form-actions">
          <button
            class="button button-secondary"
            type="button"
            @click="scenarioDialog = false"
          >
            取消</button
          ><button class="button button-primary" type="submit">保存场景</button>
        </div>
      </form>
    </div>

    <div
      v-if="importDialog"
      class="dialog-backdrop"
      @click.self="importDialog = false"
    >
      <form class="dialog dialog-wide" @submit.prevent="importScenarios">
        <div class="dialog-heading">
          <h2>导入场景 JSON</h2>
          <button type="button" @click="importDialog = false">×</button>
        </div>
        <p>
          输入场景数组，每项包含 application_id、name、goal、expected_behavior
          和可选 source。使用应用配置中显示的应用 ID。
        </p>
        <textarea
          v-model="importedJson"
          rows="14"
          :placeholder="
            JSON.stringify([
              {
                application_id: catalog.applications[0]?.id,
                name: '...',
                goal: '...',
                expected_behavior: '...',
              },
            ])
          "
        />
        <div class="form-actions">
          <button
            class="button button-secondary"
            type="button"
            @click="importDialog = false"
          >
            取消</button
          ><button class="button button-primary" type="submit">导入场景</button>
        </div>
      </form>
    </div>
  </section>
</template>
