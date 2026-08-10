<template>
  <div class="kg-view">
    <div class="page-header">
      <h1 class="page-title">知识图谱</h1>
      <p class="page-subtitle">查看已保存的知识图谱，探索材料-性能-文献关联</p>
    </div>
    <!-- 顶部：已保存图谱列表 -->
    <a-card :bordered="false" class="kg-list-card">
      <template #title>
        <span>已保存的知识图谱</span>
      </template>
      <template #extra>
        <a-space>
          <a-tag color="blue">{{ graphs.length }} 个图谱</a-tag>
          <a-button size="small" :loading="loading" @click="loadGraphs">刷新</a-button>
        </a-space>
      </template>
      <a-spin :spinning="loading">
        <a-list
          :data-source="graphs"
          :pagination="graphs.length > 5 ? { pageSize: 5, size: 'small' } : false"
        >
          <template #renderItem="{ item }">
            <a-list-item class="kg-list-item">
              <a-list-item-meta>
                <template #title>
                  <a-button type="link" class="kg-name" @click="onSelectGraph(item)">{{ item.name }}</a-button>
                </template>
                <template #description>
                  <span class="kg-meta">
                    <span>检索词：{{ item.query || '—' }}</span>
                    <span class="sep">·</span>
                    <span>{{ item.node_count }} 节点</span>
                    <span class="sep">·</span>
                    <span>{{ item.edge_count }} 关系</span>
                    <span class="sep">·</span>
                    <span>{{ item.paper_count }} 篇文献</span>
                    <span class="sep">·</span>
                    <span>{{ formatDate(item.created_at) }}</span>
                  </span>
                </template>
              </a-list-item-meta>
              <template #actions>
                <a-button size="small" type="link" @click="onSelectGraph(item)">查看</a-button>
                <a-popconfirm title="确认删除该图谱？" @confirm="onDeleteGraph(item)">
                  <a-button size="small" type="link" danger>删除</a-button>
                </a-popconfirm>
              </template>
            </a-list-item>
          </template>
          <template #emptyText>
            <EmptyState
              type="data"
              description="暂无已保存的图谱，请前往技术情报页面搜索并保存"
              action-text="前往技术情报"
              @action="router.push('/technology-intelligence')"
            />
          </template>
        </a-list>
      </a-spin>
    </a-card>

    <!-- 全屏知识图谱展示 -->
    <a-card :bordered="false" class="kg-display-card">
      <template #title>
        <span>{{ currentGraph ? currentGraph.name : '知识图谱可视化' }}</span>
      </template>
      <template #extra>
        <a-space v-if="currentGraph">
          <a-tag color="green">{{ currentGraph.node_count }} 节点</a-tag>
          <a-tag color="orange">{{ currentGraph.edge_count }} 关系</a-tag>
        </a-space>
      </template>
      <a-spin :spinning="loadingDetail">
        <KnowledgeGraph :nodes="currentNodes" :edges="currentEdges" />
      </a-spin>
    </a-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import KnowledgeGraph from '@/components/KnowledgeGraph.vue'
import EmptyState from '@/components/EmptyState.vue'
import {
  listKnowledgeGraphs,
  getKnowledgeGraph,
  deleteKnowledgeGraph,
} from '@/api/knowledge'

const router = useRouter()

const loading = ref(false)
const loadingDetail = ref(false)
const graphs = ref([])
const currentGraph = ref(null)
const currentNodes = ref([])
const currentEdges = ref([])

async function loadGraphs() {
  loading.value = true
  try {
    const data = await listKnowledgeGraphs(50)
    graphs.value = data.graphs || []
    // 自动选中第一个图谱，避免页面初始空白
    if (graphs.value.length > 0 && !currentGraph.value) {
      await onSelectGraph(graphs.value[0])
    }
  } catch {
    // 错误由拦截器处理
  } finally {
    loading.value = false
  }
}

async function onSelectGraph(item) {
  loadingDetail.value = true
  try {
    const detail = await getKnowledgeGraph(item.graph_id)
    currentGraph.value = detail
    currentNodes.value = detail.nodes || []
    currentEdges.value = detail.edges || []
  } catch {
    // 错误由拦截器处理
  } finally {
    loadingDetail.value = false
  }
}

async function onDeleteGraph(item) {
  try {
    await deleteKnowledgeGraph(item.graph_id)
    message.success(`已删除图谱 ${item.graph_id}`)
    // 如果删除的是当前展示的图谱，清空展示
    if (currentGraph.value?.graph_id === item.graph_id) {
      currentGraph.value = null
      currentNodes.value = []
      currentEdges.value = []
    }
    await loadGraphs()
  } catch {
    // 错误由拦截器处理
  }
}

function formatDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

onMounted(() => {
  loadGraphs()
})
</script>

<style scoped>
.kg-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.kg-list-card,
.kg-display-card {
  border-radius: 8px;
}

.kg-list-item {
  padding: 10px 0 !important;
}

.kg-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--primary);
  cursor: pointer;
  touch-action: manipulation;
  padding: 0;
  height: auto;
  line-height: inherit;
}

.kg-name:hover {
  text-decoration: underline;
}

.kg-meta {
  font-size: 12px;
  color: var(--text-muted, #8a92a6);
  font-variant-numeric: tabular-nums;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  min-width: 0;
}

.kg-meta .sep {
  margin: 0 4px;
  opacity: 0.5;
}
</style>
