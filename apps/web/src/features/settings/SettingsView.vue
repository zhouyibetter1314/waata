<script setup lang="ts">
import { computed } from 'vue';
import { API_BASE } from '../../api';

const isMock = computed(() => import.meta.env.VITE_API_MOCKING !== 'disabled');
const mode = computed(() => (isMock.value ? '契约 Mock' : '真实 FastAPI'));
</script>

<template>
  <section class="page settings-page">
    <div class="page-heading">
      <div>
        <div class="eyebrow">ENVIRONMENT & SETTINGS</div>
        <h1>环境与设置</h1>
        <p class="lead">
          查看前端运行方式、正式契约和后端配置边界。敏感配置只保存在后端环境中。
        </p>
      </div>
    </div>

    <div class="settings-status" :class="{ 'settings-status-mock': isMock }">
      <span class="status-dot"></span>
      <div>
        <strong>{{
          isMock ? '当前使用正式样例 Mock' : '当前连接真实 FastAPI'
        }}</strong>
        <p>
          {{
            isMock
              ? '适合独立验证前端交付条件，不代表真实 Agent 已运行。'
              : '请求通过同源 /api/v1 发送到平台后端。'
          }}
        </p>
      </div>
    </div>

    <div class="settings-layout">
      <div class="panel settings-card">
        <div class="panel-title">
          <div>
            <h2>前端运行配置</h2>
            <p>由构建环境决定，不包含服务器秘密。</p>
          </div>
        </div>
        <dl class="settings-list">
          <dt>运行模式</dt>
          <dd>{{ mode }}</dd>
          <dt>API 前缀</dt>
          <dd>
            <code>{{ API_BASE }}</code>
          </dd>
          <dt>认证策略</dt>
          <dd>同源凭据（same-origin）</dd>
          <dt>SSE 客户端</dt>
          <dd>{{ isMock ? '正式 SSE 样例重放' : '原生 EventSource' }}</dd>
          <dt>场景库位置</dt>
          <dd>当前浏览器 Local Storage</dd>
          <dt>界面语言</dt>
          <dd>简体中文</dd>
        </dl>
      </div>

      <div class="panel settings-card">
        <div class="panel-title">
          <div>
            <h2>契约状态</h2>
            <p>页面功能只消费 WAATA v0.1 正式接口。</p>
          </div>
        </div>
        <div class="contract-list">
          <div>
            <span>C1</span>
            <div>
              <strong>任务 HTTP API</strong
              ><small>提交、列表、详情、取消、报告与证据入口</small>
            </div>
            <b>已接入</b>
          </div>
          <div>
            <span>C4</span>
            <div>
              <strong>运行事件</strong
              ><small>SSE 重放、事件顺序、终态校准</small>
            </div>
            <b>已接入</b>
          </div>
          <div>
            <span>C5</span>
            <div>
              <strong>报告证据</strong
              ><small>同源授权 URL、JSON、截图与 ZIP</small>
            </div>
            <b>已接入</b>
          </div>
        </div>
      </div>

      <div class="panel settings-card settings-wide">
        <div class="panel-title">
          <div>
            <h2>模型与浏览器配置边界</h2>
            <p>Vue 不读取 DeepSeek API Key，也不直接启动 Playwright。</p>
          </div>
        </div>
        <div class="boundary-grid">
          <div>
            <span>Vue 前端</span><strong>提交 C1 请求</strong>
            <p>仅提交目标、预期、凭据引用和运行选项。</p>
          </div>
          <div>
            <span>FastAPI / Worker</span><strong>读取服务端环境</strong>
            <p>负责身份、目标授权、模型密钥、调度和证据授权。</p>
          </div>
          <div>
            <span>WAATA Package</span><strong>执行自主测试</strong>
            <p>通过注入的模型、浏览器和 ArtifactStore 运行。</p>
          </div>
        </div>
        <div class="settings-note">
          <strong>DeepSeek API Key 放在哪里？</strong>
          <p>
            由后端负责人写入部署环境或后端约定的本地环境文件，并确保不提交
            Git。前端只会看到脱敏后的运行状态和错误码。
          </p>
        </div>
      </div>

      <div class="panel settings-card settings-wide">
        <div class="panel-title">
          <div>
            <h2>当前限制</h2>
            <p>这些能力需要正式契约或真实后端完成后才能启用。</p>
          </div>
        </div>
        <ul class="settings-limitations">
          <li>
            <strong>Run 删除</strong
            ><span>C1 暂无 DELETE 端点，不能从前端伪造持久删除。</span>
          </li>
          <li>
            <strong>OpenAPI 类型生成</strong
            ><span>等待后端导出 contracts/http/openapi.json。</span>
          </li>
          <li>
            <strong>真实执行联调</strong
            ><span>等待 B02–B06 和 WAATA Package 对应任务。</span>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
