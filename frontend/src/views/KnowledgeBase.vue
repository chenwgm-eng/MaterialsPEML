<template>
  <div class="knowledge-base">
    <div class="page-header">
      <h1 class="page-title">材料知识库</h1>
      <p class="page-subtitle">以材料为中心管理知识资产：文献、性能数据、合成方法、关键主张</p>
    </div>

    <a-row :gutter="16" class="kb-body">
      <!-- 左侧：材料目录 -->
      <a-col :xs="24" :lg="8" class="kb-left">
        <a-card :bordered="false" class="catalog-card">
          <template #title>
            <span class="card-title"><DatabaseOutlined /> 材料目录</span>
          </template>
          <template #extra>
            <a-space>
              <a-input-search
                v-model:value="searchQuery"
                placeholder="搜索材料"
                size="small"
                style="width: 160px"
                @search="loadMaterials"
              />
              <a-button size="small" type="primary" @click="showCreateMaterial = true">
                <PlusOutlined />
              </a-button>
            </a-space>
          </template>

          <div class="category-filter">
            <a-tag
              :color="!filterCategory ? 'blue' : 'default'"
              class="cat-tag"
              @click="filterCategory = ''; loadMaterials()"
            >全部</a-tag>
            <a-tag
              v-for="cat in categories"
              :key="cat"
              :color="filterCategory === cat ? 'blue' : 'default'"
              class="cat-tag"
              @click="filterCategory = cat; loadMaterials()"
            >{{ cat }}</a-tag>
          </div>

          <a-spin :spinning="loadingMaterials">
            <a-list
              :data-source="materials"
              :split="false"
              class="material-list"
            >
              <template #renderItem="{ item }">
                <a-list-item
                  :class="['material-item', { active: currentMaterial?.material_id === item.material_id }]"
                  @click="onSelectMaterial(item)"
                >
                  <div class="material-item-main">
                    <div class="material-name">{{ item.canonical_name }}</div>
                    <div class="material-meta">
                      <span class="material-cat">{{ item.category || '未分类' }}</span>
                      <span class="sep">·</span>
                      <span>{{ item.paper_count }} 文献</span>
                      <span class="sep">·</span>
                      <span>{{ item.claim_count }} 主张</span>
                    </div>
                  </div>
                  <a-popconfirm title="确认删除该材料及其关联？" @confirm.stop="onDeleteMaterial(item)">
                    <a-button
                      size="small"
                      type="text"
                      danger
                      class="material-delete"
                      @click.stop
                    ><DeleteOutlined /></a-button>
                  </a-popconfirm>
                </a-list-item>
              </template>
              <template #emptyText>
                <a-empty description="暂无材料卡片，可通过技术情报检索入库或手动新建">
                  <a-button type="primary" size="small" @click="showCreateMaterial = true">
                    <PlusOutlined /> 新建材料卡片
                  </a-button>
                </a-empty>
              </template>
            </a-list>
          </a-spin>
        </a-card>
      </a-col>

      <!-- 右侧：材料详情 -->
      <a-col :xs="24" :lg="16" class="kb-right">
        <a-spin :spinning="loadingDetail">
          <EmptyState
            v-if="!currentMaterial"
            type="create"
            description="选择左侧材料查看详情，或新建一个材料卡片"
            action-text="新建材料卡片"
            class="empty-detail"
            @action="showCreateMaterial = true"
          />
          <template v-else>
            <!-- 材料基本信息 -->
            <a-card :bordered="false" class="detail-card">
              <template #title>
                <span class="card-title"><ExperimentOutlined /> {{ currentMaterial.canonical_name }}</span>
              </template>
              <template #extra>
                <a-space>
                  <a-tag :color="tierColor(currentMaterial.source_tier)">
                    {{ tierLabel(currentMaterial.source_tier) }}
                  </a-tag>
                  <a-tag :color="evidenceColor(currentMaterial.evidence_level)">
                    {{ evidenceLabel(currentMaterial.evidence_level) }}
                  </a-tag>
                </a-space>
              </template>
              <a-descriptions size="small" :column="2">
                <a-descriptions-item label="类别">{{ currentMaterial.category || '—' }}</a-descriptions-item>
                <a-descriptions-item label="别名">
                  {{ (currentMaterial.aliases || []).join('、') || '—' }}
                </a-descriptions-item>
                <a-descriptions-item label="描述" :span="2">
                  {{ currentMaterial.description || '—' }}
                </a-descriptions-item>
              </a-descriptions>
            </a-card>

            <!-- 标签页：文献 / 主张 -->
            <a-card :bordered="false" class="detail-tabs-card">
              <a-tabs v-model:activeKey="detailTab">
                <!-- 关联文献 -->
                <a-tab-pane key="papers">
                  <template #tab>
                    <FileTextOutlined /> 关联文献 ({{ currentMaterial.papers?.length || 0 }})
                  </template>
                  <a-list
                    :data-source="currentMaterial.papers || []"
                    :pagination="{ pageSize: 5, size: 'small' }"
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
                          <div class="paper-tags">
                            <a-tag size="small" :color="tierColor(item.source_tier)">
                              {{ tierLabel(item.source_tier) }}
                            </a-tag>
                            <a-tag size="small" color="default">{{ sourceLabel(item.source) }}</a-tag>
                            <a-tag v-if="item.doi" size="small" color="blue">DOI</a-tag>
                          </div>
                        </div>
                      </a-list-item>
                    </template>
                    <template #emptyText>
                      <a-empty description="暂无关联文献，可在技术情报页检索并入库文献">
                        <a-button type="primary" size="small" @click="goToTechIntelligence">
                          去技术情报检索
                        </a-button>
                      </a-empty>
                    </template>
                  </a-list>
                </a-tab-pane>

                <!-- 关键主张 -->
                <a-tab-pane key="claims">
                  <template #tab>
                    <BulbOutlined /> 关键主张 ({{ currentMaterial.claims?.length || 0 }})
                  </template>
                  <div class="claims-toolbar">
                    <a-button size="small" @click="onExtractClaims" :loading="extractingClaims">
                      <RobotOutlined /> 自动抽取主张
                    </a-button>
                    <a-button size="small" type="primary" @click="showAddClaim = true">
                      <PlusOutlined /> 手动添加
                    </a-button>
                  </div>
                  <a-list
                    :data-source="currentMaterial.claims || []"
                    class="claim-list"
                  >
                    <template #renderItem="{ item }">
                      <a-list-item class="claim-item">
                        <div class="claim-main">
                          <div class="claim-text">{{ item.claim_text }}</div>
                          <div class="claim-meta">
                            <a-tag size="small" :color="claimTypeColor(item.claim_type)">
                              {{ claimTypeLabel(item.claim_type) }}
                            </a-tag>
                            <a-tag size="small" :color="tierColor(item.source_tier)">
                              {{ tierLabel(item.source_tier) }}
                            </a-tag>
                            <a-tag size="small" :color="evidenceColor(item.evidence_level)">
                              {{ evidenceLabel(item.evidence_level) }}
                            </a-tag>
                            <span class="confidence">
                              置信度 {{ (item.confidence * 100).toFixed(0) }}%
                            </span>
                          </div>
                        </div>
                        <a-popconfirm title="确认删除该主张？" @confirm.stop="onDeleteClaim(item)">
                          <a-button size="small" type="text" danger @click.stop>
                            <DeleteOutlined />
                          </a-button>
                        </a-popconfirm>
                      </a-list-item>
                    </template>
                    <template #emptyText>
                      <a-empty description="暂无主张，点击上方按钮添加" />
                    </template>
                  </a-list>
                </a-tab-pane>
              </a-tabs>
            </a-card>
          </template>
        </a-spin>
      </a-col>
    </a-row>

    <!-- 新建材料对话框 -->
    <a-modal
      v-model:open="showCreateMaterial"
      title="新建材料卡片"
      @ok="onCreateMaterial"
    >
      <a-form layout="vertical">
        <a-form-item label="材料名称" required>
          <a-input v-model:value="newMaterial.canonical_name" placeholder="如 LLZO、NCM811" />
        </a-form-item>
        <a-form-item label="类别">
          <a-select v-model:value="newMaterial.category" allow-clear>
            <a-select-option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="newMaterial.description" :rows="3" placeholder="简要说明材料的用途、特点" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 添加主张对话框 -->
    <a-modal
      v-model:open="showAddClaim"
      title="添加主张"
      width="640px"
      @ok="onAddClaim"
    >
      <a-form layout="vertical">
        <a-form-item label="主张内容" required>
          <a-textarea
            v-model:value="newClaim.claim_text"
            :rows="3"
            placeholder="如：LLZO 在 25°C 下离子电导率达到 1.5×10⁻⁴ S/cm"
          />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="主张类型">
              <a-select v-model:value="newClaim.claim_type">
                <a-select-option value="property">性能</a-select-option>
                <a-select-option value="synthesis">合成方法</a-select-option>
                <a-select-option value="application">应用</a-select-option>
                <a-select-option value="comparison">对比结论</a-select-option>
                <a-select-option value="mechanism">机制解释</a-select-option>
                <a-select-option value="general">其他</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="来源等级">
              <a-select v-model:value="newClaim.source_tier">
                <a-select-option value="database">权威数据库</a-select-option>
                <a-select-option value="top_journal">顶级期刊</a-select-option>
                <a-select-option value="journal">同行评议期刊</a-select-option>
                <a-select-option value="internal">内部资料</a-select-option>
                <a-select-option value="preprint">预印本</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="证据强度">
              <a-select v-model:value="newClaim.evidence_level">
                <a-select-option value="production">量产验证</a-select-option>
                <a-select-option value="pilot">中试验证</a-select-option>
                <a-select-option value="lab_validated">实验室验证</a-select-option>
                <a-select-option value="literature">文献报道</a-select-option>
                <a-select-option value="computation">计算预测</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="数值 + 单位（可选）">
              <a-input-group compact>
                <a-input
                  v-model:value="newClaim.value"
                  style="width: 60%"
                  placeholder="数值或描述"
                />
                <a-input
                  v-model:value="newClaim.unit"
                  style="width: 40%"
                  placeholder="单位"
                />
              </a-input-group>
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  DatabaseOutlined, FileTextOutlined, BulbOutlined,
  PlusOutlined, DeleteOutlined, ExperimentOutlined,
  RobotOutlined,
} from '@ant-design/icons-vue'
import {
  listMaterials, getMaterial, upsertMaterial, deleteMaterial,
  createClaim, deleteClaim, extractClaims,
} from '@/api/knowledge'
import EmptyState from '@/components/EmptyState.vue'

const materials = ref([])
const currentMaterial = ref(null)
const loadingMaterials = ref(false)
const loadingDetail = ref(false)
const searchQuery = ref('')
const filterCategory = ref('')
const detailTab = ref('papers')

const router = useRouter()

// P2-3：空状态行动引导 — 跳转到技术情报页检索文献
function goToTechIntelligence() {
  router.push('/technology-intelligence')
}

const categories = ['固态电解质', '正极材料', '负极材料', '隔膜', '电解液', '其他']

const showCreateMaterial = ref(false)
const showAddClaim = ref(false)
const extractingClaims = ref(false)
const newMaterial = ref({ canonical_name: '', category: '', description: '' })
const newClaim = ref({
  claim_text: '',
  claim_type: 'property',
  source_tier: 'journal',
  evidence_level: 'literature',
  value: '',
  unit: '',
})

async function loadMaterials() {
  loadingMaterials.value = true
  try {
    const data = await listMaterials({
      query: searchQuery.value,
      category: filterCategory.value,
      limit: 100,
    })
    materials.value = data.materials || []
  } catch {
    // 拦截器处理
  } finally {
    loadingMaterials.value = false
  }
}

async function onSelectMaterial(item) {
  loadingDetail.value = true
  try {
    const detail = await getMaterial(item.material_id)
    currentMaterial.value = detail
  } catch {
    // 拦截器处理
  } finally {
    loadingDetail.value = false
  }
}

async function onCreateMaterial() {
  if (!newMaterial.value.canonical_name.trim()) {
    message.warning('请输入材料名称')
    return
  }
  try {
    const saved = await upsertMaterial({
      canonical_name: newMaterial.value.canonical_name.trim(),
      category: newMaterial.value.category,
      description: newMaterial.value.description,
    })
    message.success('材料卡片已创建')
    showCreateMaterial.value = false
    newMaterial.value = { canonical_name: '', category: '', description: '' }
    await loadMaterials()
    await onSelectMaterial(saved)
  } catch {
    // 拦截器处理
  }
}

async function onDeleteMaterial(item) {
  try {
    await deleteMaterial(item.material_id)
    message.success('已删除材料卡片')
    if (currentMaterial.value?.material_id === item.material_id) {
      currentMaterial.value = null
    }
    await loadMaterials()
  } catch {
    // 拦截器处理
  }
}

async function onAddClaim() {
  if (!newClaim.value.claim_text.trim()) {
    message.warning('请输入主张内容')
    return
  }
  try {
    await createClaim({
      material_name: currentMaterial.value.canonical_name,
      claim_text: newClaim.value.claim_text.trim(),
      claim_type: newClaim.value.claim_type,
      source_tier: newClaim.value.source_tier,
      evidence_level: newClaim.value.evidence_level,
      value: newClaim.value.value,
      unit: newClaim.value.unit,
    })
    message.success('主张已添加')
    showAddClaim.value = false
    newClaim.value = {
      claim_text: '',
      claim_type: 'property',
      source_tier: 'journal',
      evidence_level: 'literature',
      value: '',
      unit: '',
    }
    await onSelectMaterial(currentMaterial.value)
  } catch {
    // 拦截器处理
  }
}

async function onDeleteClaim(item) {
  try {
    await deleteClaim(item.claim_id)
    message.success('主张已删除')
    await onSelectMaterial(currentMaterial.value)
  } catch {
    // 拦截器处理
  }
}

async function onExtractClaims() {
  if (!currentMaterial.value) {
    message.warning('请先选择一个材料卡片')
    return
  }
  if (!currentMaterial.value.papers?.length) {
    message.warning('该材料暂无关联文献，请先在技术情报页检索入库后再抽取主张')
    return
  }
  extractingClaims.value = true
  try {
    const result = await extractClaims(currentMaterial.value.material_id, 10)
    const extracted = result.claims_extracted || 0
    if (extracted > 0) {
      message.success(`已从 ${result.papers_processed} 篇文献中抽取 ${extracted} 条主张`)
      await onSelectMaterial(currentMaterial.value)
    } else {
      message.info(`已处理 ${result.papers_processed} 篇文献，未提取到结构化主张（可能摘要信息不足）`)
    }
  } catch {
    // 拦截器处理
  } finally {
    extractingClaims.value = false
  }
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

function evidenceLabel(level) {
  const map = {
    production: '量产验证',
    pilot: '中试验证',
    lab_validated: '实验室验证',
    literature: '文献报道',
    computation: '计算预测',
  }
  return map[level] || level
}

function evidenceColor(level) {
  const map = {
    production: 'green',
    pilot: 'lime',
    lab_validated: 'cyan',
    literature: 'blue',
    computation: 'orange',
  }
  return map[level] || 'default'
}

function sourceLabel(source) {
  const map = {
    crossref: 'Crossref',
    semantic_scholar: 'Semantic Scholar',
    llm_generated: 'LLM',
    template: '模板库',
    local_kb: '本地知识库',
    internal: '内部',
    scp: 'SCP',
    search: '检索',
  }
  return map[source] || source
}

function claimTypeLabel(type) {
  const map = {
    property: '性能',
    synthesis: '合成',
    application: '应用',
    comparison: '对比',
    mechanism: '机制',
    general: '其他',
  }
  return map[type] || type
}

function claimTypeColor(type) {
  const map = {
    property: 'blue',
    synthesis: 'green',
    application: 'purple',
    comparison: 'orange',
    mechanism: 'cyan',
    general: 'default',
  }
  return map[type] || 'default'
}

onMounted(loadMaterials)
</script>

<style scoped>
.knowledge-base {
  padding: 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header { margin-bottom: 0; }
.page-title { font-size: 20px; font-weight: 600; margin: 0 0 4px 0; }
.page-subtitle { font-size: 13px; color: var(--text-muted); margin: 0; }

.kb-body { min-height: calc(100vh - 180px); }
.kb-left, .kb-right { display: flex; flex-direction: column; }

.catalog-card, .detail-card, .detail-tabs-card {
  border-radius: 8px;
}

.catalog-card { height: 100%; }
.catalog-card :deep(.ant-card-body) {
  height: calc(100% - 56px);
  overflow-y: auto;
  padding: 12px 16px;
}

.card-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 500;
}

.category-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.cat-tag { cursor: pointer; }

.material-list :deep(.ant-list-items) {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.material-item {
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

.material-item:hover { background: #f7f8fa; }
.material-item.active {
  background: #f0f5ff;
  border-color: #b7d1ff !important;
}

.material-item-main { min-width: 0; flex: 1; }
.material-name {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.material-meta {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 3px;
}
.material-meta .sep { margin: 0 5px; opacity: 0.5; }

.material-delete { flex-shrink: 0; padding: 0 4px; }

.empty-detail {
  height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.detail-card { margin-bottom: 12px; }

.detail-tabs-card {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.detail-tabs-card :deep(.ant-card-body) {
  flex: 1;
  overflow-y: auto;
}

.paper-list .paper-item {
  padding: 12px 0 !important;
  border-bottom: 1px solid #f0f0f0 !important;
}

.paper-main { display: flex; flex-direction: column; gap: 6px; width: 100%; }
.paper-title {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
  line-height: 1.4;
}
.paper-meta { font-size: 12px; color: #8a92a6; }
.paper-sep { margin: 0 5px; opacity: 0.6; }
.paper-journal { font-style: italic; }
.paper-tags { display: flex; gap: 4px; flex-wrap: wrap; }

.claims-toolbar {
  margin-bottom: 12px;
  display: flex;
  justify-content: flex-end;
}

.claim-list .claim-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 0 !important;
  border-bottom: 1px solid #f0f0f0 !important;
}

.claim-main { flex: 1; min-width: 0; }
.claim-text {
  font-size: 13px;
  color: #1a1a2e;
  line-height: 1.5;
  margin-bottom: 6px;
}
.claim-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--text-muted);
}
.confidence { margin-left: auto; }
</style>
