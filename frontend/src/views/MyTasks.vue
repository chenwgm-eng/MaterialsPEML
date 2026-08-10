<template>
  <div class="my-tasks-page">
    <div class="page-header">
      <h1 class="page-title">我的待办</h1>
      <p class="page-subtitle">统一的研发决策收件箱：实验放行卡、委员会案件、实验审批、QC审批、物料审批</p>
    </div>

    <!-- 顶部统一指标 -->
    <div class="unified-metrics">
      <div class="metric-card" v-for="stat in unifiedStats" :key="stat.key">
        <div class="metric-icon" :style="{ background: stat.bg, color: stat.color }">
          <component :is="stat.icon" />
        </div>
        <div class="metric-body">
          <div class="metric-value">{{ stat.value }}</div>
          <div class="metric-label">{{ stat.label }}</div>
        </div>
      </div>
    </div>

    <!-- 统一标签页：五个对象在同一页面切换，无子 tab 层级 -->
    <a-tabs v-model:activeKey="activeTab" class="decision-tabs" size="small">
      <a-tab-pane key="release">
        <template #tab>
          <SafetyCertificateOutlined /> 实验放行卡
          <a-badge :count="releaseCount" :number-style="{ backgroundColor: '#10b981' }" :offset="[6, -2]" />
        </template>
        <ReleaseCardCenter :embedded="true" @count-change="onReleaseCount" />
      </a-tab-pane>

      <a-tab-pane key="committee">
        <template #tab>
          <SafetyOutlined /> 委员会Case
          <a-badge :count="committeeCount" :number-style="{ backgroundColor: 'var(--info, #165dff)' }" :offset="[6, -2]" />
        </template>
        <CommitteeCenter :embedded="true" @count-change="onCommitteeCount" />
      </a-tab-pane>

      <a-tab-pane key="experiment_approval">
        <template #tab>
          <ExperimentOutlined /> 实验审批
          <a-badge :count="expApprovalCount" :number-style="{ backgroundColor: '#f59e0b' }" :offset="[6, -2]" />
        </template>
        <ApprovalCenter :embedded="true" fixed-type="experiment_order" @count-change="onExpApprovalCount" />
      </a-tab-pane>

      <a-tab-pane key="qc_approval">
        <template #tab>
          <SafetyCertificateOutlined /> QC审批
          <a-badge :count="qcApprovalCount" :number-style="{ backgroundColor: '#165dff' }" :offset="[6, -2]" />
        </template>
        <ApprovalCenter :embedded="true" fixed-type="qc_review" @count-change="onQcApprovalCount" />
      </a-tab-pane>

      <a-tab-pane key="material_approval">
        <template #tab>
          <ShopOutlined /> 物料审批
          <a-badge :count="materialApprovalCount" :number-style="{ backgroundColor: '#1d4ed8' }" :offset="[6, -2]" />
        </template>
        <ApprovalCenter :embedded="true" fixed-type="material_request" @count-change="onMaterialApprovalCount" />
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useMdmDict } from '@/utils/mdmDict'
import {
  SafetyCertificateOutlined,
  SafetyOutlined,
  ExperimentOutlined,
  ShopOutlined,
} from '@ant-design/icons-vue'
import ReleaseCardCenter from '@/views/ReleaseCardCenter.vue'
import CommitteeCenter from '@/views/CommitteeCenter.vue'
import ApprovalCenter from '@/views/ApprovalCenter.vue'
import { getReleaseCards } from '@/api/releaseCards'
import { listPendingApprovals } from '@/api/approvals'
import client from '@/api/client'

const route = useRoute()
const router = useRouter()

// 支持 URL query tab 参数映射到一级 tab
const tabMap = {
  release: 'release',
  committee: 'committee',
  approval: 'experiment_approval',
  experiment_approval: 'experiment_approval',
  qc_approval: 'qc_approval',
  material_approval: 'material_approval',
}
const activeTab = ref(tabMap[route.query.tab] || 'release')

watch(activeTab, (val) => {
  router.replace({ query: { tab: val } })
})

const releaseCount = ref(0)
const committeeCount = ref(0)
const expApprovalCount = ref(0)
const qcApprovalCount = ref(0)
const materialApprovalCount = ref(0)

function onReleaseCount(n) { releaseCount.value = n || 0 }
function onCommitteeCount(n) { committeeCount.value = n || 0 }
function onExpApprovalCount(n) { expApprovalCount.value = n || 0 }
function onQcApprovalCount(n) { qcApprovalCount.value = n || 0 }
function onMaterialApprovalCount(n) { materialApprovalCount.value = n || 0 }

const { statusOptions: mdmStatusOptions, dimensionOptions: mdmDimensionOptions } = useMdmDict()
async function loadMdmOptions() {
  try {
    await Promise.all([
      mdmStatusOptions('task'),
      mdmStatusOptions('run'),
      mdmDimensionOptions('priority'),
    ])
  } catch (e) {
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
}

// 页面加载时预取所有tab数量，无需点击tab即可显示
// 注意：三个接口均返回 {items, count}，读取 .count（.total 不存在会导致恒为 0）
async function preloadAllCounts() {
  try {
    const [releaseRes, committeeRes, expApprovalRes, qcApprovalRes, materialRes] = await Promise.all([
      getReleaseCards({ status: 'pending', limit: 1 }).catch(() => ({ count: 0 })),
      client.get('/committees/cases', { params: { status: 'pending', limit: 1 } }).catch(() => ({ count: 0 })),
      listPendingApprovals({ type: 'experiment_order', limit: 1 }).catch(() => ({ count: 0 })),
      listPendingApprovals({ type: 'qc_review', limit: 1 }).catch(() => ({ count: 0 })),
      listPendingApprovals({ type: 'material_request', limit: 1 }).catch(() => ({ count: 0 })),
    ])
    releaseCount.value = releaseRes?.count || 0
    committeeCount.value = committeeRes?.count || 0
    expApprovalCount.value = expApprovalRes?.count || 0
    qcApprovalCount.value = qcApprovalRes?.count || 0
    materialApprovalCount.value = materialRes?.count || 0
  } catch {
    // 静默失败，数量保持为0，点击tab后子组件会加载
  }
}

onMounted(() => {
  loadMdmOptions()
  preloadAllCounts()
})

const unifiedStats = computed(() => [
  {
    key: 'release',
    label: '待复核放行卡',
    value: releaseCount.value,
    icon: SafetyCertificateOutlined,
    bg: 'rgba(16, 185, 129, 0.1)',
    color: '#10b981',
  },
  {
    key: 'committee',
    label: '待处理委员会案件',
    value: committeeCount.value,
    icon: SafetyOutlined,
    bg: 'rgba(32, 80, 208, 0.1)',
    color: '#2050d0',
  },
  {
    key: 'experiment_approval',
    label: '待实验审批',
    value: expApprovalCount.value,
    icon: ExperimentOutlined,
    bg: 'rgba(245, 158, 11, 0.1)',
    color: '#f59e0b',
  },
  {
    key: 'qc_approval',
    label: '待QC审批',
    value: qcApprovalCount.value,
    icon: SafetyCertificateOutlined,
    bg: 'rgba(22, 93, 255, 0.1)',
    color: '#165dff',
  },
  {
    key: 'material_approval',
    label: '待物料审批',
    value: materialApprovalCount.value,
    icon: ShopOutlined,
    bg: 'rgba(249, 115, 22, 0.1)',
    color: '#1d4ed8',
  },
])
</script>

<style scoped>
.my-tasks-page {
  width: 100%;
  max-width: 100%;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  margin-bottom: 4px;
}

.unified-metrics {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}

.metric-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.metric-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.metric-body {
  flex: 1;
  min-width: 0;
}

.metric-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.metric-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.decision-tabs {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 12px 16px;
}

@media (max-width: 1200px) {
  .unified-metrics {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .unified-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
