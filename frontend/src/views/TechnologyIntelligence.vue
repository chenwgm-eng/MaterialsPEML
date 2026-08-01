<template>
  <div class="tech-intel">
    <div class="page-header">
      <h1 class="page-title">技术情报</h1>
      <p class="page-subtitle">搜索电池材料文献，构建知识图谱并沉淀情报资产</p>
    </div>

    <!-- 顶层标签：技术情报 / 已保存图谱 -->
    <a-tabs v-model:activeKey="activeTab" class="tech-intel-tabs">
      <a-tab-pane key="intel">
        <template #tab>
          <SearchOutlined aria-hidden="true" /> 技术情报
        </template>

        <!-- 顶部：搜索栏 -->
        <a-card class="search-card" :bordered="false">
          <div class="search-row">
            <a-input-search
              v-model:value="searchQuery"
              aria-label="搜索电池材料文献"
              placeholder="输入关键词搜索电池材料文献（如 固态电解质、NCM811、LLZO）"
              enter-button="搜索"
              size="large"
              :loading="searching"
              @search="onSearch"
            />
          </div>
          <div class="search-hints">
            <span class="hint-label">热门：</span>
            <div class="hint-chips">
              <span
                v-for="kw in hotKeywords"
                :key="kw"
                class="hint-chip"
                role="button"
                tabindex="0"
                :aria-label="`搜索 ${kw}`"
                @click="searchQuery = kw; onSearch()"
                @keydown.enter.prevent="searchQuery = kw; onSearch()"
                @keydown.space.prevent="searchQuery = kw; onSearch()"
              >
                {{ kw }}
              </span>
            </div>
          </div>
        </a-card>

        <!-- 中部：左文献列表 + 右知识图谱 -->
        <a-row :gutter="16" class="content-row">
          <a-col :xs="24" :lg="10">
            <a-card :bordered="false" class="paper-card">
              <template #title>
                <span class="card-title"><FileTextOutlined aria-hidden="true" /> 文献列表</span>
              </template>
              <template #extra>
                <a-tag color="blue">{{ papers.length }} 篇</a-tag>
              </template>
              <a-spin :spinning="searching">
                <a-list
                  :data-source="papers"
                  :pagination="papers.length > 8 ? { pageSize: 8, size: 'small' } : false"
                  class="paper-list"
                >
                  <template #renderItem="{ item }">
                    <a-list-item class="paper-item">
                      <div class="paper-main">
                        <div class="paper-title">{{ item.title }}</div>
                        <div class="paper-meta">
                          <span>{{ (item.authors || []).slice(0, 3).join('，') }}{{ (item.authors || []).length > 3 ? ' 等' : '' }}</span>
                          <span class="paper-sep">·</span>
                          <span class="paper-journal">{{ item.journal }}</span>
                          <span class="paper-sep">·</span>
                          <span>{{ item.year }}</span>
                        </div>
                        <div class="paper-abstract">{{ item.abstract }}</div>
                        <div class="paper-footer">
                          <div class="paper-keywords">
                            <span v-for="kw in (item.keywords || []).slice(0, 3)" :key="kw" class="kw-chip">
                              {{ kw }}
                            </span>
                          </div>
                          <div class="paper-indicators">
                            <a-tag
                              v-if="item.source_tier"
                              size="small"
                              :color="tierColor(item.source_tier)"
                              class="source-tag"
                            >
                              {{ tierLabel(item.source_tier) }}
                            </a-tag>
                            <a-tag
                              v-if="item.source === 'llm_generated' || item.source_tier === 'llm_generated'"
                              size="small"
                              color="warning"
                              class="source-tag"
                            >
                              <WarningOutlined /> 待核实
                            </a-tag>
                            <a-tooltip title="可信度综合来源期刊等级、引用次数、数据完整性与方法可复现性评估（0-100），仅供排序参考">
                              <span class="indicator" :class="credibilityClass(item.credibility_score)">
                                可信度 {{ item.credibility_score != null && item.credibility_score > 0 ? item.credibility_score : '—' }}
                              </span>
                            </a-tooltip>
                            <span v-if="item.adoption_status" class="indicator" :class="adoptionClass(item.adoption_status)">
                              {{ adoptionLevelLabel(item.adoption_status) }}
                            </span>
                          </div>
                        </div>
                      </div>
                    </a-list-item>
                  </template>
                  <template #emptyText>
                    <a-empty description="暂无文献，请输入关键词搜索" />
                  </template>
                </a-list>
              </a-spin>
            </a-card>
          </a-col>

          <a-col :xs="24" :lg="14">
            <a-card :bordered="false" class="graph-card">
              <template #title>
                <span class="card-title"><ShareAltOutlined aria-hidden="true" /> 知识图谱</span>
              </template>
              <template #extra>
                <a-space>
                  <a-tag color="green">{{ graphNodes.length }} 节点</a-tag>
                  <a-tag color="orange">{{ graphEdges.length }} 关系</a-tag>
                  <a-tooltip title="请先搜索并构建知识图谱" :visible="graphNodes.length ? false : undefined">
                    <a-button
                      size="small"
                      type="primary"
                      :loading="saving"
                      :disabled="!graphNodes.length"
                      @click="onSaveGraph"
                    >
                      保存图谱
                    </a-button>
                  </a-tooltip>
                </a-space>
              </template>
              <a-spin :spinning="buildingGraph">
                <div class="graph-wrap">
                  <KnowledgeGraph :nodes="graphNodes" :edges="graphEdges" @select="onNodeSelect" />
                </div>
              </a-spin>
            </a-card>
          </a-col>
        </a-row>
      </a-tab-pane>

      <!-- 已保存图谱标签页 -->
      <a-tab-pane key="saved-graphs">
        <template #tab>
          <SaveOutlined aria-hidden="true" /> 已保存图谱
        </template>

        <a-card :bordered="false" class="saved-card">
          <template #title>
            <span class="card-title"><SaveOutlined aria-hidden="true" /> 已保存图谱</span>
          </template>
          <template #extra>
            <a-button size="small" :loading="savedLoading" @click="loadSavedGraphs">刷新</a-button>
          </template>

          <div class="saved-body">
            <a-spin :spinning="savedLoading">
              <a-list
                :data-source="savedGraphs"
                class="saved-list"
                :split="false"
              >
                <template #renderItem="{ item }">
                  <a-list-item
                    :class="['saved-item', { active: currentSavedGraph?.graph_id === item.graph_id }]"
                    role="button"
                    tabindex="0"
                    :aria-label="`查看图谱 ${item.name}`"
                    @click="onSelectSavedGraph(item)"
                    @keydown.enter.prevent="onSelectSavedGraph(item)"
                    @keydown.space.prevent="onSelectSavedGraph(item)"
                  >
                    <div class="saved-item-main">
                      <div class="saved-name">{{ item.name }}</div>
                      <div class="saved-meta">
                        <span>{{ item.query || '—' }}</span>
                        <span class="sep">·</span>
                        <span>{{ item.node_count }} 节点</span>
                        <span class="sep">·</span>
                        <span>{{ item.edge_count }} 关系</span>
                        <span class="sep">·</span>
                        <span>{{ formatGraphDate(item.created_at) }}</span>
                      </div>
                    </div>
                    <a-popconfirm title="确认删除该图谱？" @confirm.stop="onDeleteSavedGraph(item)">
                      <a-button
                        size="small"
                        type="text"
                        danger
                        class="saved-delete"
                        aria-label="删除图谱"
                        @click.stop
                      >
                        <DeleteOutlined aria-hidden="true" />
                      </a-button>
                    </a-popconfirm>
                  </a-list-item>
                </template>
                <template #emptyText>
                  <a-empty description="暂无已保存的图谱，请在「技术情报」标签页搜索并保存" />
                </template>
              </a-list>
            </a-spin>

            <a-spin :spinning="savedDetailLoading" class="saved-detail">
              <KnowledgeGraph
                v-if="currentSavedNodes.length"
                :nodes="currentSavedNodes"
                :edges="currentSavedEdges"
              />
              <div v-else class="saved-detail-empty">
                <InboxOutlined aria-hidden="true" />
                <span>选择左侧图谱查看详情</span>
              </div>
            </a-spin>
          </div>
        </a-card>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  SearchOutlined, ShareAltOutlined, FileTextOutlined,
  SaveOutlined, DeleteOutlined, InboxOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'
import KnowledgeGraph from '@/components/KnowledgeGraph.vue'
import {
  searchLiterature,
  searchAndIngest,
  buildKnowledgeGraph,
  saveKnowledgeGraph,
  listKnowledgeGraphs,
  getKnowledgeGraph,
  deleteKnowledgeGraph,
} from '@/api/knowledge'

// 顶层标签：技术情报 / 已保存图谱
const activeTab = ref('intel')

const searchQuery = ref('')
const searching = ref(false)
const buildingGraph = ref(false)
const saving = ref(false)

// ── 已保存图谱状态 ──
const savedLoading = ref(false)
const savedDetailLoading = ref(false)
const savedGraphs = ref([])
const currentSavedGraph = ref(null)
const currentSavedNodes = ref([])
const currentSavedEdges = ref([])

async function loadSavedGraphs() {
  savedLoading.value = true
  try {
    const data = await listKnowledgeGraphs(50)
    savedGraphs.value = data.graphs || []
    if (savedGraphs.value.length > 0 && !currentSavedGraph.value) {
      await onSelectSavedGraph(savedGraphs.value[0])
    }
  } catch {
    // 错误由拦截器处理
  } finally {
    savedLoading.value = false
  }
}

async function onSelectSavedGraph(item) {
  savedDetailLoading.value = true
  try {
    const detail = await getKnowledgeGraph(item.graph_id)
    currentSavedGraph.value = detail
    currentSavedNodes.value = detail.nodes || []
    currentSavedEdges.value = detail.edges || []
  } catch {
    // 错误由拦截器处理
  } finally {
    savedDetailLoading.value = false
  }
}

async function onDeleteSavedGraph(item) {
  try {
    await deleteKnowledgeGraph(item.graph_id)
    message.success('已删除图谱')
    if (currentSavedGraph.value?.graph_id === item.graph_id) {
      currentSavedGraph.value = null
      currentSavedNodes.value = []
      currentSavedEdges.value = []
    }
    await loadSavedGraphs()
  } catch {
    // 错误由拦截器处理
  }
}

function formatGraphDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

// 切换到「已保存图谱」标签时懒加载列表
watch(activeTab, (val) => {
  if (val === 'saved-graphs' && savedGraphs.value.length === 0) {
    loadSavedGraphs()
  }
})

const papers = ref([])
const graphNodes = ref([])
const graphEdges = ref([])

const hotKeywords = ['固态电解质', 'NCM811', 'LLZO', '锂金属负极', '磷酸铁锂', '钠离子电池']

function credibilityClass(score) {
  if (score == null || score <= 0) return 'indicator-weak'
  if (score >= 80) return 'indicator-strong'
  if (score >= 60) return 'indicator-mid'
  return 'indicator-weak'
}

function adoptionClass(level) {
  const map = {
    adopted: 'indicator-strong',
    partially_adopted: 'indicator-mid',
    reference_only: 'indicator-weak',
    rejected: 'indicator-danger',
    pending_review: 'indicator-weak',
  }
  return map[level] || 'indicator-weak'
}

function adoptionLevelLabel(level) {
  const map = {
    adopted: '已采纳',
    partially_adopted: '部分采纳',
    reference_only: '仅参考',
    rejected: '拒绝',
    pending_review: '待复核',
  }
  return map[level] || level
}

async function onSearch() {
  const q = searchQuery.value.trim()
  if (!q) {
    message.warning('请输入搜索关键词')
    return
  }
  searching.value = true
  buildingGraph.value = true
  papers.value = []
  graphNodes.value = []
  graphEdges.value = []
  let ingestionInfo = null
  try {
    // 检索 + 入库一体化：把检索结果同步落到知识资产库
    const data = await searchAndIngest(q, 10)
    papers.value = data.papers || []
    ingestionInfo = data.ingestion || null
  } catch {
    message.error('文献搜索失败')
    papers.value = []
  }
  if (!papers.value.length) {
    message.info('未找到匹配文献')
    buildingGraph.value = false
    searching.value = false
    return
  }
  if (ingestionInfo) {
    message.success(
      `已入库 ${ingestionInfo.papers_added} 篇文献，触达 ${ingestionInfo.materials_touched} 个材料卡片`
    )
  }
  try {
    const graph = await buildKnowledgeGraph(papers.value)
    graphNodes.value = graph.nodes || []
    graphEdges.value = graph.edges || []
  } catch {
    message.error('知识图谱构建失败')
    graphNodes.value = []
    graphEdges.value = []
  }
  searching.value = false
  buildingGraph.value = false
}

function tierLabel(tier) {
  const map = {
    database: '权威数据库',
    top_journal: '顶级期刊',
    journal: '同行评议期刊',
    preprint: '预印本',
    internal: '内部资料',
    llm_generated: 'LLM 生成',
  }
  return map[tier] || tier
}

function tierColor(tier) {
  const map = {
    database: 'purple',
    top_journal: 'red',
    journal: 'blue',
    preprint: 'orange',
    internal: 'cyan',
    llm_generated: 'default',
  }
  return map[tier] || 'default'
}

function onNodeSelect(node) {
  // 节点点击由组件内 modal 处理
}

async function onSaveGraph() {
  if (!graphNodes.value.length) return
  saving.value = true
  try {
    const payload = {
      graph: { nodes: graphNodes.value, edges: graphEdges.value },
      name: `${searchQuery.value.trim()} 知识图谱`,
      query: searchQuery.value.trim(),
      paper_count: papers.value.length,
    }
    const saved = await saveKnowledgeGraph(payload)
    message.success(`图谱已保存：${saved.graph_id}`)
    await loadSavedGraphs()
  } catch {
    // 错误由拦截器处理
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.tech-intel {
  padding: 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  margin-bottom: 0;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 4px 0;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

/* ── 搜索栏 ── */
.search-card {
  border-radius: 8px;
}

.search-card :deep(.ant-card-body) {
  padding: 16px 20px;
}

.search-row :deep(.ant-input-search-button) {
  min-width: 88px;
}

.search-hints {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.hint-label {
  color: #8a92a6;
  flex-shrink: 0;
}

.hint-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.hint-chip {
  padding: 2px 8px;
  border-radius: 12px;
  background: #f5f6f8;
  color: #4a5060;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
  line-height: 1.4;
}

.hint-chip:hover {
  background: #e8eaf0;
  color: var(--primary);
}

/* ── 内容区 ── */
.content-row {
  margin: 0 !important;
}

.card-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 500;
}

.paper-card,
.graph-card {
  border-radius: 8px;
  height: 600px;
  overflow: hidden;
}

.paper-card :deep(.ant-card-head),
.graph-card :deep(.ant-card-head) {
  padding: 0 16px;
  min-height: 44px;
}

.paper-card :deep(.ant-card-body) {
  height: calc(600px - 44px);
  overflow-y: auto;
  padding: 12px 16px;
}

.graph-card :deep(.ant-card-body) {
  height: calc(600px - 44px);
  overflow: hidden;
  padding: 0;
}

.graph-wrap {
  width: 100%;
  height: 100%;
}

.graph-wrap :deep(.kg-chart),
.graph-wrap :deep(.kg-empty) {
  height: calc(600px - 44px);
}

/* ── 文献列表 ── */
.paper-list {
  height: 100%;
}

.paper-item {
  padding: 12px 0 !important;
  border-bottom: 1px solid #f0f0f0 !important;
}

.paper-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.paper-title {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a2e;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.paper-meta {
  font-size: 12px;
  color: #8a92a6;
}

.paper-sep {
  margin: 0 5px;
  opacity: 0.6;
}

.paper-journal {
  font-style: italic;
}

.paper-abstract {
  font-size: 12px;
  color: #4a5060;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.paper-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 2px;
}

.paper-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.kw-chip {
  padding: 1px 6px;
  border-radius: 10px;
  background: #f5f6f8;
  color: #5a6070;
  font-size: 11px;
  line-height: 1.4;
}

.paper-indicators {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.indicator {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 10px;
  line-height: 1.4;
  white-space: nowrap;
}

.indicator-strong {
  background: #e6f7ed;
  color: #1f8f55;
}

.indicator-mid {
  background: #fff2e0;
  color: #c76c00;
}

.indicator-weak {
  background: #f5f6f8;
  color: var(--text-muted);
}

.indicator-danger {
  background: #fff0f0;
  color: #c41d23;
}

/* ── 已保存图谱 ── */
.saved-card {
  border-radius: 8px;
}

.saved-card :deep(.ant-card-head) {
  padding: 0 16px;
  min-height: 44px;
}

.saved-body {
  display: flex;
  gap: 16px;
  height: 520px;
  overflow: hidden;
}

.saved-list {
  width: 360px;
  flex-shrink: 0;
  height: 100%;
  overflow-y: auto;
}

.saved-list :deep(.ant-list-items) {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.saved-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px !important;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
  border: 1px solid transparent !important;
}

.saved-item:hover {
  background: #f7f8fa;
}

.saved-item.active {
  background: #f0f5ff;
  border-color: #b7d1ff !important;
}

.saved-item-main {
  min-width: 0;
  flex: 1;
}

.saved-name {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.saved-meta {
  font-size: 11px;
  color: #8a92a6;
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.saved-meta .sep {
  margin: 0 5px;
  opacity: 0.5;
}

.saved-delete {
  flex-shrink: 0;
  padding: 0 4px;
}

.saved-detail {
  flex: 1;
  min-width: 0;
  height: 100%;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  overflow: hidden;
}

.saved-detail-empty {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #8a92a6;
  font-size: 13px;
}

.saved-detail-empty :deep(.anticon) {
  font-size: 28px;
  opacity: 0.5;
}

.saved-detail :deep(.kg-chart),
.saved-detail :deep(.kg-empty) {
  height: 518px;
}

/* 响应式 */
@media (max-width: 992px) {
  .paper-card,
  .graph-card {
    height: auto;
    min-height: 420px;
  }

  .graph-card :deep(.ant-card-body),
  .graph-wrap :deep(.kg-chart),
  .graph-wrap :deep(.kg-empty) {
    height: 420px;
  }

  .saved-body {
    flex-direction: column;
    height: auto;
  }

  .saved-list {
    width: 100%;
    height: auto;
    max-height: 260px;
  }

  .saved-detail {
    height: 320px;
  }

  .saved-detail :deep(.kg-chart),
  .saved-detail :deep(.kg-empty) {
    height: 318px;
  }
}
</style>
