<template>
  <div class="forbidden-result">
    <a-result
      status="403"
      title="403"
      sub-title="抱歉，您没有权限访问此页面"
    >
      <template #extra>
        <a-space>
          <a-button type="primary" @click="goHome">返回首页</a-button>
          <a-button @click="goBack">返回上一页</a-button>
        </a-space>
      </template>
      <div class="forbidden-hint">
        <p>可能原因：</p>
        <ul>
          <li>当前角色权限不足，请联系管理员提升角色</li>
          <li>该功能仅对特定角色开放（如管理员、项目经理）</li>
          <li>请尝试切换角色或登录其他账号</li>
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
.forbidden-result {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 24px;
}

.forbidden-hint {
  margin-top: 16px;
  padding: 16px 24px;
  background: var(--light-bg-hover, #fafafa);
  border-radius: 8px;
  text-align: left;
  font-size: 13px;
  color: var(--text-secondary, #595959);
  max-width: 480px;
}

.forbidden-hint p {
  margin: 0 0 8px;
  font-weight: 600;
}

.forbidden-hint ul {
  margin: 0;
  padding-left: 20px;
}

.forbidden-hint li {
  margin-bottom: 4px;
  line-height: 1.6;
}
</style>
