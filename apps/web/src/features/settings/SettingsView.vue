<script setup lang="ts">
import { API_BASE } from '../../api';
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

    <div class="settings-layout">
      <div class="panel settings-card">
        <div class="panel-title">
          <div>
            <h2>前端运行配置</h2>
          </div>
        </div>
        <dl class="settings-list">
          <dt>API 前缀</dt>
          <dd>
            <code>{{ API_BASE }}</code>
          </dd>
          <dt>请求凭据</dt>
          <dd>同源（same-origin）</dd>
          <dt>SSE 客户端</dt>
          <dd>原生 EventSource</dd>
          <dt>场景库位置</dt>
          <dd>当前浏览器 Local Storage</dd>
          <dt>界面语言</dt>
          <dd>简体中文</dd>
        </dl>
      </div>

      <div class="panel settings-card">
        <div class="panel-title">
          <div>
            <h2>接口契约</h2>
          </div>
        </div>
        <div class="contract-list">
          <div>
            <span>C1</span>
            <div>
              <strong>任务 HTTP API</strong
              ><small>提交、列表、详情、取消、报告与证据入口</small>
            </div>
          </div>
          <div>
            <span>C4</span>
            <div>
              <strong>运行事件</strong
              ><small>SSE 重放、事件顺序、终态校准</small>
            </div>
          </div>
          <div>
            <span>C5</span>
            <div>
              <strong>报告证据</strong
              ><small>同源授权 URL、JSON、截图与 ZIP</small>
            </div>
          </div>
        </div>
      </div>

      <div class="panel settings-card settings-wide">
        <div class="panel-title">
          <div>
            <h2>模型与浏览器配置边界</h2>
            <p>模型密钥和 Playwright 由服务端管理。</p>
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
          <strong>模型 API 密钥</strong>
          <p>
            在服务端部署环境或仓库根目录的本地 .env 中配置 WAATA_MODEL_API_KEY。
          </p>
        </div>
      </div>

      <div class="panel settings-card settings-wide">
        <div class="panel-title">
          <div>
            <h2>当前限制</h2>
          </div>
        </div>
        <ul class="settings-limitations">
          <li>
            <strong>Run 删除</strong><span>C1 v0.1 暂无任务删除接口。</span>
          </li>
          <li>
            <strong>Playwright Trace</strong
            ><span
              >原始 Trace
              采集关闭。运行证据包括结构化观察和按目标策略启用的截图。</span
            >
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
