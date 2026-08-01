<template>
  <div class="not-found">
    <a-result
      status="404"
      title="404"
      sub-title="抱歉，您访问的页面不存在"
    >
      <template #extra>
        <a-space>
          <a-button type="primary" @click="goHome">返回首页</a-button>
          <a-button @click="goBack">返回上一页</a-button>
        </a-space>
      </template>
      <div class="not-found-hint">
        <p>可能原因：</p>
        <ul>
          <li>页面地址已变更，请使用左侧导航栏重新进入</li>
          <li>链接已失效，请联系管理员</li>
          <li>URL 拼写错误，请检查地址栏</li>
        </ul>
      </div>
    </a-result>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.push('/')
}

function goBack() {
  router.back()
}
</script>

<style scoped>
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 24px;
}

.not-found-hint {
  margin-top: 16px;
  padding: 16px 24px;
  background: var(--light-bg-hover, #fafafa);
  border-radius: 8px;
  text-align: left;
  font-size: 13px;
  color: var(--text-secondary, #595959);
  max-width: 480px;
}

.not-found-hint p {
  margin: 0 0 8px;
  font-weight: 600;
}

.not-found-hint ul {
  margin: 0;
  padding-left: 20px;
}

.not-found-hint li {
  margin-bottom: 4px;
  line-height: 1.6;
}
</style>
