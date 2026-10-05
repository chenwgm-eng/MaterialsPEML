<template>
  <div class="material-properties">
    <div class="page-header">
      <h1 class="page-title">属性字典</h1>
      <p class="page-subtitle">按物料类型维护属性字段模板，化合物标识为所有物料类型的默认属性</p>
    </div>

    <div class="dict-layout">
      <!-- 左侧：物料类型纵向列表（数据来源于主数据） -->
      <div class="type-sidebar">
        <div class="sidebar-title">
          <AppstoreOutlined /> 物料类型
        </div>
        <a-input
          v-model:value="typeFilter"
          placeholder="搜索物料类型"
          allow-clear
          size="small"
          class="type-filter"
        >
          <template #prefix><SearchOutlined /></template>
        </a-input>
        <a-spin :spinning="typeLoading">
          <div class="type-list">
            <div
              v-for="mt in filteredMaterialTypes"
              :key="mt.value"
              class="type-item"
              :class="{ active: selectedMaterialType === mt.value }"
              role="button"
              tabindex="0"
              @click="selectMaterialType(mt.value)"
              @keydown.enter.prevent="selectMaterialType(mt.value)"
            >
              <span class="type-name">{{ mt.label }}</span>
              <a-tag class="type-count" :color="selectedMaterialType === mt.value ? 'blue' : 'default'">
                {{ typeConfiguredCount(mt.value) }}
              </a-tag>
            </div>
            <EmptyState
              v-if="filteredMaterialTypes.length === 0"
              type="search"
              description="无匹配物料类型"
              class="type-empty"
            />
          </div>
        </a-spin>
      </div>

      <!-- 右侧：属性字典信息 -->
      <div class="dict-content">
        <a-spin :spinning="loading">
          <EmptyState
            v-if="!selectedMaterialType"
            type="data"
            description="请从左侧选择物料类型"
            class="content-empty"
          />
          <template v-else>
            <div class="content-header">
              <span class="current-type">{{ currentTypeLabel }}</span>
              <a-tag color="green">{{ totalConfiguredCount }} 个已配置字段</a-tag>
              <a-tag v-if="hasNonDefaultTemplate" color="blue">已自定义模板</a-tag>
            </div>

            <a-tabs v-model:activeKey="activeCategory" type="card" class="dict-tabs">
              <a-tab-pane v-for="cat in categoryTabs" :key="cat.key">
                <template #tab>
                  <span class="tab-label">
                    <component :is="getIcon(cat.icon)" />
                    {{ cat.label_cn }}
                    <a-badge
                      :count="configuredFields(cat).length"
                      :number-style="{ backgroundColor: 'var(--primary)' }"
                    />
                  </span>
                </template>

                <div class="category-desc">{{ cat.description }}</div>

                <!-- 上半部分：已配置字段 -->
                <div class="section-header configured-header">
                  <span class="section-title">
                    <CheckCircleFilled class="section-icon configured" />
                    已配置字段
                  </span>
                  <span class="section-count num">{{ configuredFields(cat).length }} 个</span>
                </div>
                <a-table
                  :columns="configuredColumns"
                  :data-source="configuredFields(cat)"
                  :pagination="false"
                  row-key="key"
                  size="small"
                  :scroll="{ x: 640 }"
                  class="field-table configured-table"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'check'">
                      <a-checkbox
                        :checked="true"
                        :disabled="cat.key === 'identification'"
                        @change="(e) => onToggleField(cat, record, e.target.checked)"
                      />
                    </template>
                    <template v-else-if="column.key === 'key'">
                      <code class="field-key">{{ record.key }}</code>
                      <a-tag v-if="record.is_custom" color="orange" class="custom-tag">自定义</a-tag>
                    </template>
                    <template v-else-if="column.key === 'label_cn'">{{ record.label_cn }}</template>
                    <template v-else-if="column.key === 'value_type'">
                      <a-tag :color="typeColor(record.value_type)">{{ typeLabel(record.value_type) }}</a-tag>
                      <a-tag v-if="record.is_array" color="blue">列表</a-tag>
                    </template>
                    <template v-else-if="column.key === 'unit'">
                      <span v-if="record.unit" class="num">{{ record.unit }}</span>
                      <span v-else class="text-muted">-</span>
                    </template>
                    <template v-else-if="column.key === 'action'">
                      <a-button
                        v-if="record.is_custom"
                        type="link"
                        danger
                        size="small"
                        @click="onRemoveCustom(record)"
                      >删除</a-button>
                      <span v-else class="text-muted">内置</span>
                    </template>
                  </template>
                </a-table>

                <!-- 下半部分：未配置字段（化合物标识 Tab 无此区域） -->
                <template v-if="cat.key !== 'identification'">
                  <div class="section-header unconfigured-header">
                    <span class="section-title">
                      <PlusCircleOutlined class="section-icon unconfigured" />
                      未配置字段
                    </span>
                    <span class="section-count num">{{ unconfiguredFields(cat).length }} 个</span>
                  </div>
                  <a-table
                    :columns="unconfiguredColumns"
                    :data-source="unconfiguredFields(cat)"
                    :pagination="false"
                    row-key="key"
                    size="small"
                    :scroll="{ x: 560 }"
                    class="field-table unconfigured-table"
                  >
                    <template #bodyCell="{ column, record }">
                      <template v-if="column.key === 'check'">
                        <a-checkbox
                          :disabled="!isAdmin"
                          :checked="isAdmin ? undefined : false"
                          @change="(e) => onToggleField(cat, record, e.target.checked)"
                        />
                      </template>
                      <template v-else-if="column.key === 'key'">
                        <code class="field-key">{{ record.key }}</code>
                        <a-tag v-if="record.is_custom" color="orange" class="custom-tag">自定义</a-tag>
                      </template>
                      <template v-else-if="column.key === 'label_cn'">{{ record.label_cn }}</template>
                      <template v-else-if="column.key === 'value_type'">
                        <a-tag :color="typeColor(record.value_type)">{{ typeLabel(record.value_type) }}</a-tag>
                      </template>
                      <template v-else-if="column.key === 'unit'">
                        <span v-if="record.unit" class="num">{{ record.unit }}</span>
                        <span v-else class="text-muted">-</span>
                      </template>
                    </template>
                  </a-table>
                </template>

                <!-- 新增该 Tab 的自定义属性（化合物标识 Tab 为默认属性，不允许添加） -->
                <div v-if="cat.key !== 'identification'" class="add-custom-row">
                  <span class="add-custom-label">
                    <PlusOutlined /> 新增「{{ cat.label_cn }}」自定义属性
                  </span>
                  <div class="add-custom-form">
                    <a-input
                      v-model:value="getCustomForm(cat.key).key"
                      placeholder="键名(英文)"
                      size="small"
                      style="width: 170px"
                    />
                    <a-input
                      v-model:value="getCustomForm(cat.key).label_cn"
                      placeholder="中文名称"
                      size="small"
                      style="width: 150px"
                    />
                    <a-select
                      v-model:value="getCustomForm(cat.key).value_type"
                      :options="typeOptions"
                      size="small"
                      style="width: 120px"
                    />
                    <a-input
                      v-model:value="getCustomForm(cat.key).unit"
                      placeholder="单位"
                      size="small"
                      style="width: 90px"
                    />
                    <a-button
                      type="primary"
                      size="small"
                      :loading="addingCustom[cat.key]"
                      :disabled="!isAdmin"
                      @click="onAddCustom(cat)"
                    >添加</a-button>
                    <span v-if="!isAdmin" class="text-muted" style="font-size: 11px">（仅管理员可编辑模板）</span>
                  </div>
                </div>
              </a-tab-pane>
            </a-tabs>
          </template>
        </a-spin>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  TagOutlined,
  ExperimentOutlined,
  WarningOutlined,
  AppstoreOutlined,
  ThunderboltOutlined,
  PlusOutlined,
  ProfileOutlined,
  SearchOutlined,
  FireOutlined,
  BranchesOutlined,
  CheckCircleFilled,
  PlusCircleOutlined,
} from '@ant-design/icons-vue'
import {
  getCategories,
  addCustomField,
  removeCustomField,
  getMaterialTypeTemplates,
  updateMaterialTypeTemplate,
} from '@/api/properties'
import {
  DEFAULT_INDUSTRIAL_CATEGORIES,
  industrialCategoryLabel,
} from '@/constants/materialTypes'
import { useMdmDict } from '@/utils/mdmDict'
import EmptyState from '@/components/EmptyState.vue'
import { useAuth } from '@/composables/useAuth'


const iconMap = {
  TagOutlined,
  ExperimentOutlined,
  WarningOutlined,
  AppstoreOutlined,
  ThunderboltOutlined,
  PlusOutlined,
  ProfileOutlined,
  FireOutlined,
  BranchesOutlined,
}

function getIcon(name) {
  return iconMap[name] || ProfileOutlined
}

// ── 数据状态 ──────────────────────────────────────────────────
const categories = ref([])
const loading = ref(false)
const typeLoading = ref(false)
const activeCategory = ref('identification')
const typeFilter = ref('')

// 物料类型：从主数据加载（MDM classifications domain='material'），DEFAULT 兜底
const materialTypes = ref([...DEFAULT_INDUSTRIAL_CATEGORIES])
const selectedMaterialType = ref('')

// 自定义字段/模板编辑为管理员操作（后端 addCustomField/updateMaterialTypeTemplate 为 ADMIN only）
const { isAdmin } = useAuth()

// 模板：{ [material_type]: field_keys[] }，响应式对象
const templateMap = reactive({})

// 每个 Tab 的自定义属性表单
const customForms = reactive({})
const addingCustom = reactive({})

const { classificationOptions } = useMdmDict()

// ── 计算属性 ──────────────────────────────────────────────────
// 化合物标识字段 key 列表（所有物料类型默认含有的属性）
const identificationKeys = computed(() => {
  const cat = categories.value.find((c) => c.key === 'identification')
  return cat ? cat.fields.map((f) => f.key) : []
})

// 当前选中物料类型的模板字段 key 列表
const currentTemplateFieldKeys = computed(() => {
  if (!selectedMaterialType.value) return []
  return templateMap[selectedMaterialType.value] || []
})

// 物料类型过滤
const filteredMaterialTypes = computed(() => {
  const kw = typeFilter.value.trim().toLowerCase()
  if (!kw) return materialTypes.value
  return materialTypes.value.filter(
    (mt) =>
      String(mt.label).toLowerCase().includes(kw) ||
      String(mt.value).toLowerCase().includes(kw),
  )
})

// 当前物料类型标签
const currentTypeLabel = computed(() => {
  const mt = materialTypes.value.find((m) => m.value === selectedMaterialType.value)
  return mt ? mt.label : selectedMaterialType.value
})

// 是否存在非默认模板（即除标识字段外还配置了其它字段）
const hasNonDefaultTemplate = computed(() => {
  const keys = currentTemplateFieldKeys.value
  if (keys.length === 0) return false
  return keys.some((k) => !identificationKeys.value.includes(k))
})

// 已配置字段总数
const totalConfiguredCount = computed(() => {
  let n = 0
  for (const cat of categoryTabs.value) {
    n += configuredFields(cat).length
  }
  return n
})

// 分类 Tab 列表：仅展示有字段的分类，化合物标识置首
const categoryTabs = computed(() => {
  const tabs = categories.value.filter((c) => (c.fields || []).length > 0)
  return tabs.sort((a, b) => {
    if (a.key === 'identification') return -1
    if (b.key === 'identification') return 1
    return 0
  })
})

// ── 字段分区 ──────────────────────────────────────────────────
function configuredFields(cat) {
  if (cat.key === 'identification') return cat.fields || []
  const keys = new Set(currentTemplateFieldKeys.value)
  return (cat.fields || []).filter((f) => keys.has(f.key))
}

function unconfiguredFields(cat) {
  if (cat.key === 'identification') return []
  const keys = new Set(currentTemplateFieldKeys.value)
  return (cat.fields || []).filter((f) => !keys.has(f.key))
}

// 物料类型在左侧列表中显示的已配置字段数（无模板时回退到标识字段数）
function typeConfiguredCount(mt) {
  const keys = templateMap[mt] || []
  if (keys.length === 0) return identificationKeys.value.length
  return keys.length
}

// ── 模板操作 ──────────────────────────────────────────────────
async function loadTemplateMap() {
  try {
    const res = await getMaterialTypeTemplates()
    const templates = res?.templates || []
    for (const t of templates) {
      templateMap[t.material_type] = t.field_keys || []
    }
  } catch {
    /* handled by interceptor */
  }
}

async function fetchCategories() {
  try {
    const res = await getCategories()
    categories.value = res.categories || []
    // 为每个分类初始化自定义属性表单
    for (const cat of categories.value) {
      if (!customForms[cat.key]) {
        customForms[cat.key] = { key: '', label_cn: '', value_type: 'float', unit: '' }
      }
    }
  } catch {
    /* handled */
  }
}

async function loadMaterialTypes() {
  typeLoading.value = true
  try {
    const opts = await classificationOptions('material')
    if (opts && opts.length > 0) {
      materialTypes.value = opts
    }
  } catch {
    /* 保留 DEFAULT 兜底 */
  } finally {
    typeLoading.value = false
  }
}

function selectMaterialType(value) {
  selectedMaterialType.value = value
  activeCategory.value = 'identification'
}

// 勾选/取消勾选字段：自动加入/移出模板并保存
async function onToggleField(cat, record, checked) {
  if (cat.key === 'identification') return // 标识字段锁定，不可取消
  const mt = selectedMaterialType.value
  if (!mt) return
  const keys = new Set(currentTemplateFieldKeys.value)
  if (checked) {
    keys.add(record.key)
  } else {
    keys.delete(record.key)
  }
  // 保存时始终包含化合物标识字段
  const allKeys = [...new Set([...identificationKeys.value, ...keys])]
  try {
    await updateMaterialTypeTemplate(mt, allKeys)
    templateMap[mt] = allKeys
    message.success(
      checked ? `已添加「${record.label_cn}」` : `已移除「${record.label_cn}」`,
    )
  } catch {
    /* handled by interceptor */
  }
}

// 新增该 Tab 的自定义属性
function getCustomForm(catKey) {
  if (!customForms[catKey]) {
    customForms[catKey] = { key: '', label_cn: '', value_type: 'float', unit: '' }
  }
  return customForms[catKey]
}

const KEY_PATTERN = /^[a-zA-Z][a-zA-Z0-9_]{0,63}$/

async function onAddCustom(cat) {
  const form = getCustomForm(cat.key)
  if (!form.key.trim() || !form.label_cn.trim()) {
    message.warning('请填写字段键名和中文名称')
    return
  }
  if (!KEY_PATTERN.test(form.key.trim())) {
    message.warning('键名必须以字母开头，仅含字母/数字/下划线，长度 1-64')
    return
  }
  const mt = selectedMaterialType.value
  if (!mt) {
    message.warning('请先选择物料类型')
    return
  }
  addingCustom[cat.key] = true
  const labelForMsg = form.label_cn.trim()
  const keyForMsg = form.key.trim()
  try {
    // 1. 创建自定义字段（归入当前 Tab 的分类）
    await addCustomField({
      key: keyForMsg,
      label_cn: labelForMsg,
      value_type: form.value_type,
      unit: form.unit.trim(),
      category: cat.key,
    })
    // 2. 加入当前物料类型的模板
    const keys = new Set(currentTemplateFieldKeys.value)
    keys.add(keyForMsg)
    const allKeys = [...new Set([...identificationKeys.value, ...keys])]
    await updateMaterialTypeTemplate(mt, allKeys)
    templateMap[mt] = allKeys
    // 3. 重置表单
    form.key = ''
    form.label_cn = ''
    form.unit = ''
    // 4. 刷新分类（让新字段出现在对应分类下）
    await fetchCategories()
    message.success(`自定义字段「${labelForMsg}」已添加并加入模板`)
  } catch {
    /* handled by interceptor */
  } finally {
    addingCustom[cat.key] = false
  }
}

function onRemoveCustom(record) {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除自定义字段「${record.label_cn}」(${record.key})吗？该字段将从所有物料类型模板中移除。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await removeCustomField(record.key)
        // 从所有模板中清除该 key
        for (const mt of Object.keys(templateMap)) {
          templateMap[mt] = (templateMap[mt] || []).filter((k) => k !== record.key)
        }
        await fetchCategories()
        message.success('字段已删除')
      } catch {
        /* handled */
      }
    },
  })
}

// ── 表格列定义 ──────────────────────────────────────────────────
const configuredColumns = [
  { title: '', key: 'check', width: 46, align: 'center' },
  { title: '键名', key: 'key', width: 200 },
  { title: '中文名称', key: 'label_cn', width: 160 },
  { title: '数据类型', key: 'value_type', width: 120 },
  { title: '单位', key: 'unit', width: 90 },
  { title: '操作', key: 'action', width: 80, fixed: 'right' },
]

const unconfiguredColumns = [
  { title: '', key: 'check', width: 46, align: 'center' },
  { title: '键名', key: 'key', width: 200 },
  { title: '中文名称', key: 'label_cn', width: 160 },
  { title: '数据类型', key: 'value_type', width: 120 },
  { title: '单位', key: 'unit', width: 90 },
]

const typeOptions = [
  { label: '数值（浮点）', value: 'float' },
  { label: '数值（整数）', value: 'int' },
  { label: '文本', value: 'str' },
  { label: '列表', value: 'list' },
  { label: '对象', value: 'dict' },
]

function typeColor(t) {
  const map = {
    float: 'green',
    int: 'blue',
    str: 'orange',
    list: 'purple',
    dict: 'cyan',
  }
  return map[t] || 'default'
}

function typeLabel(t) {
  const map = {
    float: '数值',
    int: '整数',
    str: '文本',
    list: '列表',
    dict: '对象',
  }
  return map[t] || t
}

// ── 初始化 ──────────────────────────────────────────────────
async function fetchData() {
  loading.value = true
  try {
    await Promise.all([fetchCategories(), loadMaterialTypes(), loadTemplateMap()])
    // 默认选中第一个物料类型
    if (!selectedMaterialType.value && materialTypes.value.length > 0) {
      selectMaterialType(materialTypes.value[0].value)
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.material-properties {
  width: 100%;
  max-width: 100%;
}

.page-header {
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 4px 0;
  color: var(--text-primary);
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.dict-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

/* 左侧物料类型列表 */
.type-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 12px;
  position: sticky;
  top: 12px;
}

.sidebar-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.type-filter {
  margin-bottom: 10px;
}

.type-list {
  max-height: calc(100vh - 220px);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.type-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
  outline: none;
}

.type-item:hover {
  background: var(--light-bg);
  border-color: var(--border);
}

.type-item.active {
  background: rgba(249, 115, 22, 0.08);
  border-color: var(--primary);
}

.type-item:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.type-name {
  font-size: 13px;
  color: var(--text-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.type-item.active .type-name {
  font-weight: 600;
  color: var(--primary);
}

.type-count {
  font-size: 11px;
  margin: 0;
  flex-shrink: 0;
}

.type-empty {
  padding: 24px 0;
}

/* 右侧属性字典内容 */
.dict-content {
  flex: 1;
  min-width: 0;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 16px;
}

.content-empty {
  padding: 60px 0;
}

.content-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.current-type {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.dict-tabs {
  width: 100%;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.category-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 12px;
  padding: 6px 10px;
  background: var(--light-bg);
  border-radius: 6px;
}

/* 分区标题 */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 6px 6px 0 0;
  margin-top: 12px;
}

.section-header:first-of-type {
  margin-top: 0;
}

.configured-header {
  background: rgba(82, 196, 26, 0.08);
  border-bottom: 1px solid rgba(82, 196, 26, 0.2);
}

.unconfigured-header {
  background: var(--light-bg);
  border-bottom: 1px solid var(--border);
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.section-icon.configured {
  color: var(--success);
}

.section-icon.unconfigured {
  color: var(--text-secondary);
}

.section-count {
  font-size: 12px;
  color: var(--text-secondary);
}

.field-table {
  margin-bottom: 4px;
}

.unconfigured-table :deep(.ant-table-tbody > tr > td) {
  color: var(--text-secondary);
}

.field-key {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--primary);
  background: rgba(249, 115, 22, 0.08);
  padding: 2px 6px;
  border-radius: 4px;
}

.custom-tag {
  margin-left: 6px;
}

/* 新增自定义属性行 */
.add-custom-row {
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--light-bg);
  border: 1px dashed var(--border);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.add-custom-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.add-custom-form {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.text-muted {
  color: var(--text-secondary);
}

.num {
  font-variant-numeric: tabular-nums;
}
</style>
