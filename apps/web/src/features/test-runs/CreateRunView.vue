<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { createRun, isApiError, type CreateRunRequest } from '../../api';
import {
  DEFAULT_AGENT_STEPS,
  validateRunRequest,
  type RunFormErrors,
} from './validation';

const router = useRouter();
const submitting = ref(false);
const requestError = ref('');
const requestId = ref('');
const errors = ref<RunFormErrors>({});
const form = reactive({
  target_url: '',
  goal: '',
  expected_behavior: '',
  credential_ref: '',
  headless: true,
  max_steps_per_case: DEFAULT_AGENT_STEPS,
});

function requestValue(): CreateRunRequest {
  return {
    target_url: form.target_url.trim(),
    goal: form.goal.trim(),
    expected_behavior: form.expected_behavior.trim(),
    credential_ref: form.credential_ref.trim() || null,
    options: {
      headless: form.headless,
      max_steps_per_case: form.max_steps_per_case,
    },
  };
}

async function submit(): Promise<void> {
  if (submitting.value) return;
  const value = requestValue();
  errors.value = validateRunRequest(value);
  requestError.value = '';
  requestId.value = '';
  if (Object.keys(errors.value).length) return;
  submitting.value = true;
  try {
    const created = await createRun(value);
    await router.push({
      name: 'run-detail',
      params: { runId: created.run_id },
    });
  } catch (error) {
    requestError.value =
      error instanceof Error ? error.message : '提交任务失败';
    if (isApiError(error)) requestId.value = error.requestId ?? '';
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <section class="page create-page">
    <div class="page-heading">
      <div>
        <div class="eyebrow">NEW TEST RUN</div>
        <h1>创建自主测试</h1>
        <p class="lead">
          描述目标应用、测试目标和可验证的预期行为，WAATA 将为本次提交分配独立
          Run ID。
        </p>
      </div>
      <RouterLink class="button button-secondary" to="/runs"
        >查看运行记录</RouterLink
      >
    </div>

    <div class="create-layout">
      <form class="panel form-panel" novalidate @submit.prevent="submit">
        <div class="form-section-heading">
          <span class="section-index">01</span>
          <div>
            <h2>测试目标</h2>
            <p>填写已获授权的 HTTP(S) 地址和自然语言任务。</p>
          </div>
        </div>

        <div class="form-grid">
          <label>
            <span>目标地址 <b>*</b></span>
            <input
              v-model="form.target_url"
              name="target_url"
              autocomplete="url"
              placeholder="例如：https://app.example.test/"
              :aria-invalid="Boolean(errors.target_url)"
            />
            <small v-if="errors.target_url" class="field-error">{{
              errors.target_url
            }}</small>
          </label>

          <label>
            <span>自然语言测试目标 <b>*</b></span>
            <textarea
              v-model="form.goal"
              name="goal"
              rows="4"
              placeholder="例如：打开登录页并查看表单"
              :aria-invalid="Boolean(errors.goal)"
            />
            <small v-if="errors.goal" class="field-error">{{
              errors.goal
            }}</small>
          </label>

          <label>
            <span>预期行为 <b>*</b></span>
            <textarea
              v-model="form.expected_behavior"
              name="expected_behavior"
              rows="4"
              placeholder="例如：登录页显示邮箱和密码输入框"
              :aria-invalid="Boolean(errors.expected_behavior)"
            />
            <small class="field-hint">尽量描述可观察、可判定的页面结果。</small>
            <small
              v-if="
                form.goal.includes('{tag}') ||
                form.expected_behavior.includes('{tag}')
              "
              class="field-hint"
              role="status"
            >
              如果是从场景示例复制的内容，请把目标和预期里的
              <code>{tag}</code> 换成同一个测试编号。
            </small>
            <small v-if="errors.expected_behavior" class="field-error">
              {{ errors.expected_behavior }}
            </small>
          </label>
        </div>

        <div class="form-divider"></div>

        <div class="form-section-heading">
          <span class="section-index">02</span>
          <div>
            <h2>运行选项</h2>
            <p>凭据只填写后端授权引用，禁止输入账号、密码或 API Key。</p>
          </div>
        </div>

        <div class="form-grid compact-form-grid">
          <label>
            <span>凭据引用（可选）</span>
            <input
              v-model="form.credential_ref"
              name="credential_ref"
              autocomplete="off"
            />
          </label>

          <div class="form-options">
            <label>
              <span>每用例 Agent 步骤上限</span>
              <input
                v-model.number="form.max_steps_per_case"
                type="number"
                name="max_steps_per_case"
                min="1"
                :aria-invalid="Boolean(errors.max_steps_per_case)"
              />
              <small v-if="errors.max_steps_per_case" class="field-error">
                {{ errors.max_steps_per_case }}
              </small>
            </label>
            <label class="toggle-card">
              <input v-model="form.headless" type="checkbox" name="headless" />
              <span class="toggle" aria-hidden="true"></span>
              <span
                ><strong>无头浏览器运行</strong
                ><small>后台执行，不显示浏览器窗口</small></span
              >
            </label>
          </div>
        </div>

        <div v-if="requestError" class="alert alert-error" role="alert">
          <strong>{{ requestError }}</strong>
          <small v-if="requestId">请求 ID：{{ requestId }}</small>
        </div>

        <div class="form-actions">
          <RouterLink class="button button-secondary" to="/runs"
            >取消</RouterLink
          >
          <button
            class="button button-primary"
            type="submit"
            :disabled="submitting"
          >
            <span v-if="submitting" class="spinner" aria-hidden="true"></span>
            {{ submitting ? '正在提交…' : '提交任务' }}
          </button>
        </div>
      </form>

      <aside class="create-guide">
        <div class="panel guide-card">
          <span class="guide-icon" aria-hidden="true">✓</span>
          <h2>提交前检查</h2>
          <ul>
            <li>目标属于已授权的测试环境</li>
            <li>目标地址不包含用户名和密码</li>
            <li>预期结果能够通过页面证据验证</li>
            <li>凭据仅使用服务端引用名称</li>
          </ul>
        </div>
        <div class="guide-note">
          <strong>提交后</strong>
          <p>页面会打开新任务的详情，你可以在那里查看排队状态和执行进度。</p>
        </div>
      </aside>
    </div>
  </section>
</template>
