<template>
  <div class="material-design">
    <a-tabs
      v-model:activeKey="activeTab"
      class="material-tabs"
      @change="onTabChange"
    >
      <a-tab-pane key="candidate" tab="候选材料设计">
        <CandidateWorkbench />
      </a-tab-pane>
      <a-tab-pane key="predict" tab="性质预测">
        <Prediction />
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CandidateWorkbench from '@/views/CandidateWorkbench.vue'
import Prediction from '@/views/Prediction.vue'

const route = useRoute()
const router = useRouter()

const activeTab = ref(route.query.tab === 'predict' ? 'predict' : 'candidate')

function onTabChange(key) {
  const query = { ...route.query }
  if (key === 'predict') {
    query.tab = 'predict'
  } else {
    delete query.tab
  }
  router.replace({ path: '/workbench', query })
}

// 支持外部通过 query.tab=predict 直接定位到「性质预测」页签
watch(
  () => route.query.tab,
  (tab) => {
    if (tab === 'predict') activeTab.value = 'predict'
  },
)
</script>

<style scoped>
.material-design {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.material-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.material-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 0;
  padding: 0 16px;
  background: var(--light-bg-card, #fff);
  border-bottom: 1px solid var(--border, #e8e8e8);
  flex-shrink: 0;
}

.material-tabs :deep(.ant-tabs-content-holder) {
  flex: 1;
  min-height: 0;
}

.material-tabs :deep(.ant-tabs-content),
.material-tabs :deep(.ant-tabs-tabpane) {
  height: 100%;
  min-height: 0;
}
</style>