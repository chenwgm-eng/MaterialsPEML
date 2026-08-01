<template>
  <div class="error-result">
    <a-result
      status="error"
      :title="title"
      :sub-title="subTitle"
    >
      <template #extra>
        <a-space>
          <a-button v-if="showRetry" type="primary" @click="$emit('retry')">
            <ReloadOutlined /> 重试
          </a-button>
          <a-button v-if="showHome" @click="goHome">返回首页</a-button>
          <a-button v-if="showBack" @click="goBack">返回上一页</a-button>
        </a-space>
      </template>
      <div v-if="details && details.length" class="error-details">
        <p>错误详情：</p>
        <ul>
          <li v-for="(item, idx) in details" :key="idx">{{ item }}</li>
        </ul>
      </div>
    </a-result>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ReloadOutlined } from '@ant-design/icons-vue'
import { MESSAGES } from '@/constants/glossary'

defineProps({
  title: {
    type: String,
    default: MESSAGES.loadFailed,
  },
  subTitle: {
    type: String,
    default: '抱歉，页面加载过程中出现错误，请稍后重试',
  },
  details: {
    type: Array,
    default: () => [],
  },
  showRetry: {
    type: Boolean,
    default: true,
  },
  showHome: {
    type: Boolean,
    default: true,
  },
  showBack: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['retry'])

const router = useRouter()

function goHome() {
  router.push('/')
}

function goBack() {
  router.back()
}
</script>

<style scoped>
.error-result {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
  padding: 24px;
}

.error-details {
  margin-top: 16px;
  padding: 16px 24px;
  background: var(--error-bg, rgba(245, 63, 63, 0.06));
  border-radius: 8px;
  text-align: left;
  font-size: 13px;
  color: var(--text-secondary, #595959);
  max-width: 560px;
}

.error-details p {
  margin: 0 0 8px;
  font-weight: 600;
  color: var(--error, #f53f3f);
}

.error-details ul {
  margin: 0;
  padding-left: 20px;
}

.error-details li {
  margin-bottom: 4px;
  line-height: 1.6;
}
</style>
