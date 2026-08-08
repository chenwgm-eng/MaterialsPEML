<template>
  <div class="mdm-center">
    <div class="page-header">
      <h1 class="page-title">主数据治理</h1>
      <p class="page-subtitle">统一管理状态码、单位、分类、物料、设备、工艺等主数据，确保跨业务流程数据一致性</p>
    </div>

    <a-spin :spinning="loading">
      <a-row :gutter="12" class="mdm-body">
        <!-- 左侧：主数据分类树 -->
        <a-col :span="5">
          <a-card class="tree-card" :bordered="false" size="small">
            <template #title>
              <span class="card-title"><AppstoreOutlined /> 主数据分类</span>
            </template>
            <a-input-search
              v-model:value="searchKeyword"
              placeholder="搜索分类"
              size="small"
              style="margin-bottom: 8px"
              allow-clear
            />
            <a-tree
              :tree-data="filteredTreeData"
              v-model:selectedKeys="selectedKeys"
              v-model:expandedKeys="expandedKeys"
              :default-expand-all="true"
              @select="onSelectNode"
              class="mdm-tree"
            />
          </a-card>
        </a-col>

        <!-- 右侧：主数据表格 -->
        <a-col :span="19">
          <a-card class="table-card" :bordered="false" size="small">
            <template #title>
              <span class="card-title">
                <component :is="currentNode?.icon || 'TableOutlined'" />
                {{ currentNode?.title || '请选择分类' }}
                <a-tag v-if="tableData.length > 0" color="blue" style="margin-left: 8px">
                  {{ tableData.length }} 条
                </a-tag>
              </span>
            </template>
            <template #extra>
              <a-space>
                <a-input-search
                  v-if="tableData.length > 0"
                  v-model:value="dataFilter"
                  placeholder="筛选数据"
                  size="small"
                  style="width: 200px"
                  allow-clear
                />
                <a-tooltip title="新增主数据">
                  <a-button
                    v-if="canCreate"
                    type="primary"
                    size="small"
                    @click="openCreateModal"
                  >
                    <PlusOutlined /> 新增
                  </a-button>
                </a-tooltip>
                <a-tooltip title="刷新数据">
                  <a-button size="small" @click="loadTableData" :loading="loading">
                    <ReloadOutlined />
                  </a-button>
                </a-tooltip>
              </a-space>
            </template>

            <!-- 数据表格 -->
            <a-table
              v-if="currentNode && tableColumns.length > 0"
              :columns="tableColumns"
              :data-source="filteredTableData"
              :pagination="{ pageSize: 15, size: 'small', showTotal: (t) => `共 ${t} 条` }"
              :scroll="{ x: 'max-content', y: 'calc(100vh - 340px)' }"
              size="small"
              row-key="code"
              :loading="loading"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'is_active'">
                  <a-switch
                    v-if="canToggle"
                    size="small"
                    :checked="!!record.is_active"
                    :loading="!!togglingKeys[recordKey(record)]"
                    @change="(checked) => onToggleActive(record, checked)"
                  />
                  <a-tag v-else :color="record.is_active ? 'green' : 'default'">
                    {{ record.is_active ? '启用' : '停用' }}
                  </a-tag>
                </template>
                <template v-else-if="column.key === 'description'">
                  <a-tooltip :title="record.description">
                    <span class="text-ellipsis">{{ record.description || '—' }}</span>
                  </a-tooltip>
                </template>
                <template v-else-if="column.key === 'actions'">
                  <a-button
                    v-if="currentNode?.key === 'units'"
                    type="link"
                    size="small"
                    @click="openUnitVersionDrawer(record)"
                  >
                    <HistoryOutlined /> 版本历史
                  </a-button>
                </template>
              </template>
            </a-table>

            <!-- 未选择分类时的占位 -->
            <div v-else class="mdm-empty-guide">
              <EmptyState
                type="data"
                description="请从左侧选择主数据分类。选择分类后可查看、新增、编辑该分类下的主数据记录"
              />
            </div>
          </a-card>
        </a-col>
      </a-row>
    </a-spin>

    <!-- 新增主数据弹窗 -->
    <a-modal
      v-model:open="createModalOpen"
      :title="`新增 ${currentNode?.title || ''}`"
      width="640px"
      :confirm-loading="creating"
      :mask-closable="false"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitCreate"
    >
      <a-form
        ref="createFormRef"
        :model="createForm"
        :label-col="{ span: 7 }"
        :wrapper-col="{ span: 16 }"
        size="small"
      >
        <a-form-item
          v-for="field in createFormFields"
          :key="field.key"
          :label="field.title"
          :name="field.key"
          :rules="field.required ? [{ required: true, message: `${field.title}必填` }] : []"
        >
          <a-select
            v-if="field.isFk"
            v-model:value="createForm[field.key]"
            :options="field.options"
            :loading="field.loading"
            :placeholder="`选择${field.title}`"
            show-search
            allow-clear
            :filter-option="(input, option) => (option?.label || '').toLowerCase().includes(input.toLowerCase())"
          />
          <a-switch
            v-else-if="field.isBool"
            v-model:checked="createForm[field.key]"
          />
          <a-input-number
            v-else-if="field.isNumeric"
            v-model:value="createForm[field.key]"
            style="width: 100%"
            :step="field.step"
          />
          <a-date-picker
            v-else-if="field.isDate"
            v-model:value="createForm[field.key]"
            style="width: 100%"
            value-format="YYYY-MM-DD"
          />
          <a-textarea
            v-else-if="field.isLongText"
            v-model:value="createForm[field.key]"
            :rows="2"
            :placeholder="`输入${field.title}`"
          />
          <a-input
            v-else
            v-model:value="createForm[field.key]"
            :placeholder="`输入${field.title}`"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 单位版本历史 Drawer（T-018 / T-019） -->
    <a-drawer
      v-model:open="unitVersionDrawerOpen"
      :title="`版本历史 - ${unitVersionDrawerUnitCode}`"
      width="640px"
      placement="right"
    >
      <template #extra>
        <a-space>
          <span style="font-size: 12px; color: var(--text-muted)">
            已选 {{ unitVersionSelected.length }} / 2
          </span>
          <a-button
            type="primary"
            size="small"
            :disabled="unitVersionSelected.length !== 2"
            :loading="unitCompareLoading"
            @click="openUnitCompareDrawer"
          >
            <SwapOutlined /> 对比
          </a-button>
          <a-button size="small" @click="loadUnitVersions" :loading="unitVersionsLoading">
            <ReloadOutlined />
          </a-button>
        </a-space>
      </template>

      <a-spin :spinning="unitVersionsLoading">
        <a-empty v-if="unitVersions.length === 0" description="暂无版本记录（更新单位后会产生版本快照）" />
        <a-list v-else :data-source="unitVersions" item-layout="vertical">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #title>
                  <a-checkbox
                    :checked="unitVersionSelected.includes(item.version_id)"
                    :disabled="!unitVersionSelected.includes(item.version_id) && unitVersionSelected.length >= 2"
                    @change="(e) => onToggleVersionSelect(item, e.target.checked)"
                    style="margin-right: 8px"
                  />
                  <span>版本 {{ item.version_number }}</span>
                  <a-tag v-if="item.is_active" color="green" style="margin-left: 8px">活跃</a-tag>
                </template>
                <template #description>
                  <div>{{ item.change_summary || '—' }}</div>
                  <div style="font-size: 12px; color: var(--text-muted)">
                    {{ item.created_at }} · {{ item.created_by || 'system' }} · {{ item.version_id }}
                  </div>
                </template>
              </a-list-item-meta>
              <template #actions>
                <a-button type="link" size="small" @click="viewUnitVersionDetail(item)">
                  <EyeOutlined /> 查看详情
                </a-button>
                <a-popconfirm
                  :title="`确定激活版本 ${item.version_number}？将用该版本数据覆盖当前记录。`"
                  @confirm="onActivateUnitVersion(item)"
                  :disabled="item.is_active"
                >
                  <a-button type="link" size="small" :disabled="item.is_active">
                    <RollbackOutlined /> 激活
                  </a-button>
                </a-popconfirm>
              </template>
            </a-list-item>
          </template>
        </a-list>
      </a-spin>
    </a-drawer>

    <!-- 版本详情 Modal -->
    <a-modal
      v-model:open="unitVersionDetailModalOpen"
      :title="`版本详情 - v${unitVersionDetail.version_number || ''}`"
      width="600px"
      :footer="null"
    >
      <a-descriptions :column="1" size="small" bordered>
        <a-descriptions-item label="版本号">{{ unitVersionDetail.version_number }}</a-descriptions-item>
        <a-descriptions-item label="版本 ID">{{ unitVersionDetail.version_id }}</a-descriptions-item>
        <a-descriptions-item label="是否活跃">
          <a-tag :color="unitVersionDetail.is_active ? 'green' : 'default'">
            {{ unitVersionDetail.is_active ? '活跃' : '非活跃' }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="变更说明">{{ unitVersionDetail.change_summary || '—' }}</a-descriptions-item>
        <a-descriptions-item label="创建时间">{{ unitVersionDetail.created_at }}</a-descriptions-item>
        <a-descriptions-item label="创建人">{{ unitVersionDetail.created_by || 'system' }}</a-descriptions-item>
      </a-descriptions>
      <a-divider style="margin: 12px 0" />
      <h4 style="margin: 0 0 8px 0">快照数据</h4>
      <a-descriptions :column="1" size="small" bordered>
        <a-descriptions-item
          v-for="(val, key) in unitVersionDetail.snapshot"
          :key="key"
          :label="key"
        >
          <span v-if="typeof val === 'boolean'">{{ val ? '是' : '否' }}</span>
          <span v-else>{{ val === null || val === '' ? '—' : val }}</span>
        </a-descriptions-item>
      </a-descriptions>
    </a-modal>

    <!-- 版本对比 Drawer（T-019：侧边并排展示） -->
    <a-drawer
      v-model:open="unitCompareDrawerOpen"
      :title="`版本对比 - ${unitVersionDrawerUnitCode}`"
      width="75%"
      placement="right"
    >
      <a-spin :spinning="unitCompareLoading">
        <div v-if="unitCompareResult">
          <a-alert
            type="info"
            show-icon
            style="margin-bottom: 12px"
            :message="`版本 A: v${unitCompareResult.version_a?.version_number || ''}  →  版本 B: v${unitCompareResult.version_b?.version_number || ''}`"
            description="差异字段已高亮：黄色=修改，绿色=新增，红色=删除"
          />
          <a-table
            :columns="unitCompareColumns"
            :data-source="unitCompareResult.diff"
            :pagination="false"
            size="small"
            row-key="field"
            :scroll="{ y: 'calc(100vh - 280px)' }"
            :row-class-name="(record) => `version-diff-row version-diff-${record.change_type}`"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'change_type'">
                <a-tag :color="diffTagColor(record.change_type)">
                  {{ diffTagText(record.change_type) }}
                </a-tag>
              </template>
              <template v-else-if="column.key === 'old_value'">
                <span>{{ formatSnapshotValue(record.old_value) }}</span>
              </template>
              <template v-else-if="column.key === 'new_value'">
                <span>{{ formatSnapshotValue(record.new_value) }}</span>
              </template>
            </template>
          </a-table>
        </div>
        <a-empty v-else description="请选择两个版本进行对比" />
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import EmptyState from '@/components/EmptyState.vue'
import {
  AppstoreOutlined, TableOutlined, ReloadOutlined, PlusOutlined,
  SettingOutlined, DashboardOutlined, ExperimentOutlined,
  ToolOutlined, EnvironmentOutlined, InboxOutlined,
  ProfileOutlined, FileTextOutlined, ApartmentOutlined,
  SafetyOutlined, BranchesOutlined, ArrowLeftOutlined,
  HistoryOutlined, SwapOutlined, EyeOutlined, RollbackOutlined,
} from '@ant-design/icons-vue'
import * as mdmApi from '@/api/mdm'

// ──────────────────────────────────────────────────────────────
// 域元数据：主键列 + 是否可新增/启停
// ──────────────────────────────────────────────────────────────
const DOMAIN_META = {
  'status-codes':              { pk: ['domain', 'code'],            canToggle: true,  canCreate: true },
  'classifications':           { pk: ['code'],                       canToggle: true,  canCreate: true },
  'units':                     { pk: ['unit_code'],                  canToggle: true,  canCreate: true },
  'unit-conversions':          { pk: [],                              canToggle: false, canCreate: true },
  'standards':                 { pk: ['standard_code'],               canToggle: true,  canCreate: true },
  'ghs-classes':               { pk: ['ghs_code'],                    canToggle: true,  canCreate: true },
  'dimensions':                { pk: ['domain', 'code'],             canToggle: true,  canCreate: true },
  'sample-types':             { pk: ['type_code'],                   canToggle: true,  canCreate: true },
  'sample-status-transitions': { pk: [],                              canToggle: false, canCreate: false },
  'locations':                 { pk: ['location_id'],                 canToggle: true,  canCreate: true },
  'containers':               { pk: ['container_code'],              canToggle: true,  canCreate: true },
  'logistics-types':          { pk: ['type_code'],                    canToggle: true,  canCreate: true },
  'equipment-templates':      { pk: ['template_code'],               canToggle: true,  canCreate: true },
  'equipment-capabilities':   { pk: ['capability_code'],             canToggle: true,  canCreate: true },
  'material-categories':      { pk: ['category_code'],               canToggle: false, canCreate: true },
  'properties':               { pk: ['property_id'],                 canToggle: true,  canCreate: true },
  'test-methods':             { pk: ['method_id'],                    canToggle: true,  canCreate: true },
  'test-items':               { pk: ['item_id'],                     canToggle: true,  canCreate: true },
  'specifications':            { pk: ['spec_id'],                     canToggle: true,  canCreate: true },
  'inspection-capabilities':  { pk: ['capability_id'],               canToggle: true,  canCreate: true },
  'process-routes':           { pk: ['route_id'],                    canToggle: true,  canCreate: true },
  'process-steps':            { pk: ['step_id'],                     canToggle: true,  canCreate: true },
  'process-parameters':       { pk: ['parameter_id'],                canToggle: true,  canCreate: true },
  'documents':                { pk: ['document_id'],                 canToggle: true,  canCreate: true },
}

// FK 字段 → 选项加载器映射（创建表单中以下拉选择呈现）
const FK_LOADERS = {
  default_unit:           () => mdmApi.listUnits().then(r => (r.data?.units || r.units || []).map(u => ({ value: u.unit_code, label: `${u.unit_code} (${u.name})` }))),
  default_location_id:    () => mdmApi.listLocations().then(r => (r.data?.locations || r.locations || []).map(l => ({ value: l.location_id, label: l.name }))),
  category_code:          () => mdmApi.listClassifications('material').then(r => (r.data?.classifications || r.classifications || []).map(c => ({ value: c.code, label: c.label }))),
  standard_code:          () => mdmApi.listStandards().then(r => (r.data?.standards || r.standards || []).map(s => ({ value: s.standard_code, label: `${s.standard_code} ${s.name}` }))),
  property_id:            () => mdmApi.listProperties().then(r => (r.data?.properties || r.properties || []).map(p => ({ value: p.property_id, label: p.name }))),
  method_id:              () => mdmApi.listTestMethods().then(r => (r.data?.test_methods || r.test_methods || []).map(m => ({ value: m.method_id, label: m.name }))),
  test_method_id:         () => mdmApi.listTestMethods().then(r => (r.data?.test_methods || r.test_methods || []).map(m => ({ value: m.method_id, label: m.name }))),
  item_id:                () => mdmApi.listTestItems().then(r => (r.data?.test_items || r.test_items || []).map(i => ({ value: i.item_id, label: i.name }))),
  location_id:            () => mdmApi.listLocations().then(r => (r.data?.locations || r.locations || []).map(l => ({ value: l.location_id, label: l.name }))),
  template_code:          () => mdmApi.listEquipmentTemplates().then(r => (r.data?.equipment_templates || r.equipment_templates || []).map(t => ({ value: t.template_code, label: t.name }))),
}

// 数值类列名后缀/集合（用于推断输入框类型）
const NUMERIC_KEYS = new Set(['sort_order', 'default_retention_days', 'capacity', 'capacity_value', 'factor', 'offset_value', 'target_value', 'min_value', 'max_value', 'default_value', 'range_min', 'range_max', 'accuracy', 'detection_limit', 'step_order'])
// 布尔类列名集合
const BOOL_KEYS = new Set(['is_active', 'is_base', 'is_hazardous', 'is_hazardous_compatible', 'requires_approval'])
// 系统自动生成列（创建表单中不展示）
const SYSTEM_KEYS = new Set(['created_at', 'updated_at', 'code_id', 'id', 'dim_code'])

// ──────────────────────────────────────────────────────────────
// 分类树配置
// ──────────────────────────────────────────────────────────────
// 每个叶子节点配置：key, title, icon, loader(数据加载函数), columns(表格列)
const treeData = ref([
  {
    title: '参考字典', key: 'ref', icon: 'DashboardOutlined',
    children: [
      _leaf('status-codes', '状态码', 'SettingOutlined', mdmApi.listStatusCodes, [
        { title: '域', dataIndex: 'domain', key: 'domain', width: 120, fixed: 'left' },
        { title: '编码', dataIndex: 'code', key: 'code', width: 200 },
        { title: '标签', dataIndex: 'label', key: 'label', width: 150 },
        { title: '排序', dataIndex: 'sort_order', key: 'sort_order', width: 60 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
        { title: '说明', dataIndex: 'description', key: 'description', ellipsis: true },
      ]),
      _leaf('classifications', '分类码', 'ApartmentOutlined', mdmApi.listClassifications, [
        { title: '域', dataIndex: 'domain', key: 'domain', width: 120, fixed: 'left' },
        { title: '编码', dataIndex: 'code', key: 'code', width: 180 },
        { title: '父级', dataIndex: 'parent_code', key: 'parent_code', width: 150 },
        { title: '标签', dataIndex: 'label', key: 'label', width: 150 },
        { title: '排序', dataIndex: 'sort_order', key: 'sort_order', width: 60 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
        { title: '说明', dataIndex: 'description', key: 'description', ellipsis: true },
      ]),
      _leaf('units', '标准单位', 'DashboardOutlined', mdmApi.listUnits, [
        { title: '编码', dataIndex: 'unit_code', key: 'unit_code', width: 120, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 120 },
        { title: '符号', dataIndex: 'symbol', key: 'symbol', width: 80 },
        { title: '维度', dataIndex: 'dimension', key: 'dimension', width: 120 },
        { title: '基本单位', dataIndex: 'is_base', key: 'is_base', width: 80, customRender: ({ text }) => text ? '是' : '否' },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
        { title: '操作', key: 'actions', width: 110, fixed: 'right' },
      ]),
      _leaf('unit-conversions', '单位换算', 'DashboardOutlined', mdmApi.listUnitConversions, [
        { title: '源单位', dataIndex: 'from_unit', key: 'from_unit', width: 120 },
        { title: '目标单位', dataIndex: 'to_unit', key: 'to_unit', width: 120 },
        { title: '系数', dataIndex: 'factor', key: 'factor', width: 100 },
        { title: '偏移量', dataIndex: 'offset_value', key: 'offset_value', width: 100 },
      ]),
      _leaf('standards', '方法标准', 'SafetyOutlined', mdmApi.listStandards, [
        { title: '编码', dataIndex: 'standard_code', key: 'standard_code', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 250 },
        { title: '发布机构', dataIndex: 'issuer', key: 'issuer', width: 120 },
        { title: '版本', dataIndex: 'version', key: 'version', width: 100 },
        { title: '生效日期', dataIndex: 'effective_date', key: 'effective_date', width: 120 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('ghs-classes', 'GHS 危害分类', 'SafetyOutlined', mdmApi.listGhsClasses, [
        { title: '编码', dataIndex: 'ghs_code', key: 'ghs_code', width: 120, fixed: 'left' },
        { title: '标签', dataIndex: 'label', key: 'label', width: 200 },
        { title: '危害等级', dataIndex: 'hazard_level', key: 'hazard_level', width: 120 },
        { title: '象形图', dataIndex: 'pictogram', key: 'pictogram', width: 120 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('dimensions', '通用维度', 'ProfileOutlined', mdmApi.listDimensions, [
        { title: '域', dataIndex: 'domain', key: 'domain', width: 150, fixed: 'left' },
        { title: '编码', dataIndex: 'code', key: 'code', width: 180 },
        { title: '标签', dataIndex: 'label', key: 'label', width: 150 },
        { title: '排序', dataIndex: 'sort_order', key: 'sort_order', width: 60 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
        { title: '说明', dataIndex: 'description', key: 'description', ellipsis: true },
      ]),
    ],
  },
  {
    title: '物料与样品', key: 'material', icon: 'InboxOutlined',
    children: [
      _leaf('material-categories', '物料分类', 'ApartmentOutlined', mdmApi.listMaterialCategories, [
        { title: '编码', dataIndex: 'category_code', key: 'category_code', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '父级', dataIndex: 'parent_code', key: 'parent_code', width: 150 },
        { title: '默认存储条件', dataIndex: 'default_storage_conditions', key: 'default_storage_conditions', width: 150 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('sample-types', '样品类型', 'InboxOutlined', mdmApi.listSampleTypes, [
        { title: '编码', dataIndex: 'type_code', key: 'type_code', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '默认单位', dataIndex: 'default_unit', key: 'default_unit', width: 100 },
        { title: '默认存储条件', dataIndex: 'default_storage_condition', key: 'default_storage_condition', width: 150 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('sample-status-transitions', '样品状态迁移', 'BranchesOutlined', mdmApi.listSampleStatusTransitions, [
        { title: '源状态', dataIndex: 'from_status', key: 'from_status', width: 150 },
        { title: '目标状态', dataIndex: 'to_status', key: 'to_status', width: 150 },
        { title: '需审批', dataIndex: 'requires_approval', key: 'requires_approval', width: 100, customRender: ({ text }) => text ? '是' : '否' },
        { title: '说明', dataIndex: 'description', key: 'description', ellipsis: true },
      ]),
      _leaf('locations', '位置', 'EnvironmentOutlined', mdmApi.listLocations, [
        { title: '编码', dataIndex: 'location_id', key: 'location_id', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '父级', dataIndex: 'parent_id', key: 'parent_id', width: 150 },
        { title: '类型', dataIndex: 'location_type', key: 'location_type', width: 120 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('containers', '容器', 'InboxOutlined', mdmApi.listContainers, [
        { title: '编码', dataIndex: 'container_code', key: 'container_code', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '容量', dataIndex: 'capacity', key: 'capacity', width: 100 },
        { title: '单位', dataIndex: 'unit', key: 'unit', width: 80 },
        { title: '材质', dataIndex: 'material', key: 'material', width: 120 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('logistics-types', '物流类型', 'ApartmentOutlined', mdmApi.listLogisticsTypes, [
        { title: '编码', dataIndex: 'type_code', key: 'type_code', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
    ],
  },
  {
    title: '设备模板', key: 'equipment', icon: 'ToolOutlined',
    children: [
      _leaf('equipment-templates', '设备模板', 'ToolOutlined', mdmApi.listEquipmentTemplates, [
        { title: '编码', dataIndex: 'template_code', key: 'template_code', width: 200, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '分类', dataIndex: 'category_code', key: 'category_code', width: 150 },
        { title: '制造商', dataIndex: 'manufacturer', key: 'manufacturer', width: 150 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('equipment-capabilities', '设备能力', 'ToolOutlined', mdmApi.listEquipmentCapabilities, [
        { title: '编码', dataIndex: 'capability_code', key: 'capability_code', width: 200, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '分类', dataIndex: 'category', key: 'category', width: 150 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
    ],
  },
  {
    title: 'CIMC 模型', key: 'cimc', icon: 'ExperimentOutlined',
    children: [
      _leaf('properties', '特性', 'ProfileOutlined', mdmApi.listProperties, [
        { title: '编码', dataIndex: 'property_id', key: 'property_id', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '符号', dataIndex: 'symbol', key: 'symbol', width: 80 },
        { title: '单位', dataIndex: 'unit', key: 'unit', width: 100 },
        { title: '方向', dataIndex: 'direction', key: 'direction', width: 100 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('test-methods', '测试方法', 'ExperimentOutlined', mdmApi.listTestMethods, [
        { title: '编码', dataIndex: 'method_id', key: 'method_id', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 250 },
        { title: '标准', dataIndex: 'standard_code', key: 'standard_code', width: 150 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('test-items', '测试指标', 'ProfileOutlined', mdmApi.listTestItems, [
        { title: '编码', dataIndex: 'item_id', key: 'item_id', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '特性', dataIndex: 'property_id', key: 'property_id', width: 150 },
        { title: '方法', dataIndex: 'method_id', key: 'method_id', width: 150 },
        { title: '单位', dataIndex: 'unit', key: 'unit', width: 100 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('specifications', '规格', 'ProfileOutlined', mdmApi.listSpecifications, [
        { title: '编码', dataIndex: 'spec_id', key: 'spec_id', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('inspection-capabilities', '质检能力', 'SafetyOutlined', mdmApi.listInspectionCapabilities, [
        { title: '编码', dataIndex: 'capability_id', key: 'capability_id', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '方法', dataIndex: 'method_id', key: 'method_id', width: 150 },
        { title: '位置', dataIndex: 'location_id', key: 'location_id', width: 150 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
    ],
  },
  {
    title: '工艺路线', key: 'process', icon: 'BranchesOutlined',
    children: [
      _leaf('process-routes', '工艺路线', 'BranchesOutlined', mdmApi.listProcessRoutes, [
        { title: '编码', dataIndex: 'route_id', key: 'route_id', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '材料类型', dataIndex: 'material_type', key: 'material_type', width: 120 },
        { title: '版本', dataIndex: 'version', key: 'version', width: 80 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('process-steps', '工艺步骤', 'BranchesOutlined', mdmApi.listProcessSteps, [
        { title: '编码', dataIndex: 'step_id', key: 'step_id', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '分类', dataIndex: 'category', key: 'category', width: 150 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
      _leaf('process-parameters', '工艺参数', 'ProfileOutlined', mdmApi.listProcessParameters, [
        { title: '编码', dataIndex: 'parameter_id', key: 'parameter_id', width: 180, fixed: 'left' },
        { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
        { title: '单位', dataIndex: 'unit', key: 'unit', width: 100 },
        { title: '类型', dataIndex: 'parameter_type', key: 'parameter_type', width: 120 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
    ],
  },
  {
    title: '文档版本', key: 'docs', icon: 'FileTextOutlined',
    children: [
      _leaf('documents', '文档', 'FileTextOutlined', mdmApi.listDocuments, [
        { title: '编码', dataIndex: 'document_id', key: 'document_id', width: 180, fixed: 'left' },
        { title: '标题', dataIndex: 'title', key: 'title', width: 250 },
        { title: '类型', dataIndex: 'document_type', key: 'document_type', width: 120 },
        { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
        { title: '负责人', dataIndex: 'owner', key: 'owner', width: 120 },
        { title: '启用', dataIndex: 'is_active', key: 'is_active', width: 80 },
      ]),
    ],
  },
])

function _leaf(key, title, icon, loader, columns) {
  return { key, title, icon, isLeaf: true, _loader: loader, _columns: columns }
}

// ──────────────────────────────────────────────────────────────
// 状态
// ──────────────────────────────────────────────────────────────
const loading = ref(false)
const selectedKeys = ref([])
const expandedKeys = ref(['ref', 'material', 'equipment', 'cimc', 'process', 'docs'])
const searchKeyword = ref('')
const dataFilter = ref('')
const tableData = ref([])
const currentNode = ref(null)

const iconMap = {
  DashboardOutlined, SettingOutlined, ExperimentOutlined, ToolOutlined,
  EnvironmentOutlined, InboxOutlined, ProfileOutlined, FileTextOutlined,
  ApartmentOutlined, SafetyOutlined, BranchesOutlined, AppstoreOutlined, TableOutlined,
}

const filteredTreeData = computed(() => {
  if (!searchKeyword.value) return treeData.value
  const kw = searchKeyword.value.toLowerCase()
  const filterNode = (nodes) => {
    return nodes.map(n => {
      if (n.isLeaf) {
        return n.title.toLowerCase().includes(kw) ? n : null
      }
      const children = filterNode(n.children || []).filter(Boolean)
      return children.length > 0 ? { ...n, children } : null
    }).filter(Boolean)
  }
  return filterNode(treeData.value)
})

const tableColumns = computed(() => currentNode.value?._columns || [])

const filteredTableData = computed(() => {
  if (!dataFilter.value) return tableData.value
  const kw = dataFilter.value.toLowerCase()
  return tableData.value.filter(row => {
    return Object.values(row).some(v =>
      v != null && String(v).toLowerCase().includes(kw)
    )
  })
})

// ──────────────────────────────────────────────────────────────
// 域元数据派生：是否可新增 / 可启停
// ──────────────────────────────────────────────────────────────
const canCreate = computed(() => {
  const d = currentNode.value?.key
  return !!(d && DOMAIN_META[d]?.canCreate)
})
const canToggle = computed(() => {
  const d = currentNode.value?.key
  return !!(d && DOMAIN_META[d]?.canToggle)
})

// 复合主键的路径段拼接：用于 PATCH /mdm/{domain}/{pk}/active
function recordKey(record) {
  const d = currentNode.value?.key
  const pk = d ? (DOMAIN_META[d]?.pk || []) : []
  if (pk.length === 0) {
    // 没有主键列时退化为对象引用哈希
    return JSON.stringify(record).slice(0, 64)
  }
  return pk.map(k => record?.[k] ?? '').join('/')
}

// ──────────────────────────────────────────────────────────────
// 事件处理
// ──────────────────────────────────────────────────────────────
function onSelectNode(keys, { node }) {
  if (!node.isLeaf) return
  currentNode.value = node
  dataFilter.value = ''
  togglingKeys.value = {}
  loadTableData()
}

async function loadTableData() {
  if (!currentNode.value?._loader) return
  loading.value = true
  try {
    const data = await currentNode.value._loader()
    // 后端返回格式：{ xxx: [...], count: n } 或 [...]（client 响应拦截器已剥离 resp.data）
    const list = Array.isArray(data) ? data : (data.status_codes || data.classifications || data.units || data.unit_conversions || data.standards || data.ghs_classes || data.dimensions || data.sample_types || data.sample_status_transitions || data.locations || data.containers || data.logistics_types || data.equipment_templates || data.equipment_capabilities || data.material_categories || data.properties || data.test_methods || data.test_items || data.specifications || data.inspection_capabilities || data.process_routes || data.process_steps || data.process_parameters || data.documents || [])
    tableData.value = list
  } catch (e) {
    console.error('加载主数据失败:', e)
    message.error('加载主数据失败，请稍后重试或联系管理员')
    tableData.value = []
  } finally {
    loading.value = false
  }
}

// ──────────────────────────────────────────────────────────────
// 启用/停用切换
// ──────────────────────────────────────────────────────────────
const togglingKeys = ref({})

async function onToggleActive(record, checked) {
  const domain = currentNode.value?.key
  const pkPath = recordKey(record)
  if (!domain || !pkPath || pkPath.includes('undefined')) {
    message.error('无法识别主键，请刷新后重试')
    return
  }
  togglingKeys.value[pkPath] = true
  try {
    await mdmApi.toggleActive(domain, pkPath, checked)
    // 本地更新
    const pk = DOMAIN_META[domain]?.pk || []
    const target = tableData.value.find(r => pk.every(k => String(r[k]) === String(record[k])))
    if (target) target.is_active = checked
    message.success(`${checked ? '启用' : '停用'}成功`)
  } catch (e) {
    console.error('切换状态失败:', e)
    message.error('切换状态失败: ' + (e.response?.data?.detail || e.message))
    // 回滚 UI 由 a-switch 自动同步 checked（target 已更新失败，下次刷新会还原）
  } finally {
    togglingKeys.value[pkPath] = false
    delete togglingKeys.value[pkPath]
  }
}

// ──────────────────────────────────────────────────────────────
// 新增主数据弹窗
// ──────────────────────────────────────────────────────────────
const createModalOpen = ref(false)
const creating = ref(false)
const createFormRef = ref(null)
const createForm = ref({})
const createFormFields = ref([])
const fkOptionsCache = {}  // 同一 FK 字段在当前会话内只拉取一次

// 字段类型推断
function _inferField(col) {
  const key = col.dataIndex || col.key
  const title = col.title || key
  const domain = currentNode.value?.key
  const pkList = domain ? (DOMAIN_META[domain]?.pk || []) : []
  const isPk = pkList.includes(key)
  // 系统自动生成列
  const isSystem = SYSTEM_KEYS.has(key)
  // is_active 默认 true，不展示在表单
  if (key === 'is_active' || isSystem) return null

  const isFk = !!FK_LOADERS[key]
  const isBool = BOOL_KEYS.has(key)
  const isNumeric = NUMERIC_KEYS.has(key)
  const isDate = key === 'effective_date'
  const isLongText = key === 'description'
    || key.endsWith('_req') || key.endsWith('_formula')
    || key.endsWith('_conditions') || key === 'notes'
  const step = (key === 'sort_order' || key === 'step_order') ? 1
    : (key === 'capacity' || key === 'capacity_value' || key === 'default_retention_days') ? 1
    : 0.01
  return {
    key, title,
    isFk, isBool, isNumeric, isDate, isLongText, step,
    required: isPk,
    options: [], loading: false,
  }
}

async function _loadFkOptions(field) {
  if (!field.isFk) return
  if (fkOptionsCache[field.key]) {
    field.options = fkOptionsCache[field.key]
    return
  }
  field.loading = true
  try {
    const opts = await FK_LOADERS[field.key]()
    fkOptionsCache[field.key] = opts
    field.options = opts
  } catch (e) {
    console.error(`加载 ${field.title} 选项失败:`, e)
    field.options = []
  } finally {
    field.loading = false
  }
}

function openCreateModal() {
  if (!currentNode.value?._columns) return
  // 重建字段列表
  const fields = []
  for (const col of currentNode.value._columns) {
    const f = _inferField(col)
    if (f) fields.push(f)
  }
  createFormFields.value = fields
  // 初始化表单值：布尔默认 false，数值默认 null，其它默认 ''
  const form = {}
  for (const f of fields) {
    if (f.isBool) form[f.key] = false
    else if (f.isNumeric) form[f.key] = null
    else if (f.isDate) form[f.key] = null
    else form[f.key] = ''
  }
  createForm.value = form
  createModalOpen.value = true
  // 异步加载所有 FK 选项
  for (const f of fields) {
    if (f.isFk) _loadFkOptions(f)
  }
}

async function submitCreate() {
  const domain = currentNode.value?.key
  if (!domain) return
  // 表单校验
  try {
    await createFormRef.value?.validate()
  } catch {
    return
  }
  // 清理空值与无效值
  const payload = {}
  for (const [k, v] of Object.entries(createForm.value)) {
    if (v === null || v === undefined || v === '') continue
    payload[k] = v
  }
  creating.value = true
  try {
    await mdmApi.createItem(domain, payload)
    message.success('新增成功')
    createModalOpen.value = false
    await loadTableData()
  } catch (e) {
    console.error('新增失败:', e)
    message.error('新增失败，请稍后重试或联系管理员')
  } finally {
    creating.value = false
  }
}

// ──────────────────────────────────────────────────────────────
// 单位版本管理（T-018 / T-019）
// ──────────────────────────────────────────────────────────────
const unitVersionDrawerOpen = ref(false)
const unitVersionDrawerUnitCode = ref('')
const unitVersions = ref([])
const unitVersionsLoading = ref(false)
const unitVersionSelected = ref([])  // 选中的 version_id 列表，最多 2 个

const unitVersionDetailModalOpen = ref(false)
const unitVersionDetail = ref({})

const unitCompareDrawerOpen = ref(false)
const unitCompareResult = ref(null)
const unitCompareLoading = ref(false)

const unitCompareColumns = [
  { title: '字段', dataIndex: 'field', key: 'field', width: 140, fixed: 'left' },
  { title: '版本 A (旧)', dataIndex: 'old_value', key: 'old_value', ellipsis: true },
  { title: '版本 B (新)', dataIndex: 'new_value', key: 'new_value', ellipsis: true },
  { title: '变更类型', dataIndex: 'change_type', key: 'change_type', width: 100 },
]

async function openUnitVersionDrawer(record) {
  unitVersionDrawerUnitCode.value = record.unit_code
  unitVersionDrawerOpen.value = true
  unitVersionSelected.value = []
  unitCompareResult.value = null
  await loadUnitVersions()
}

async function loadUnitVersions() {
  if (!unitVersionDrawerUnitCode.value) return
  unitVersionsLoading.value = true
  try {
    const data = await mdmApi.listUnitVersions(unitVersionDrawerUnitCode.value)
    unitVersions.value = data.versions || []
  } catch (e) {
    console.error('加载版本历史失败:', e)
    message.error('加载版本历史失败: ' + (e.response?.data?.detail || e.message))
    unitVersions.value = []
  } finally {
    unitVersionsLoading.value = false
  }
}

function onToggleVersionSelect(item, checked) {
  const idx = unitVersionSelected.value.indexOf(item.version_id)
  if (checked && idx === -1) {
    if (unitVersionSelected.value.length >= 2) return
    unitVersionSelected.value = [...unitVersionSelected.value, item.version_id]
  } else if (!checked && idx > -1) {
    unitVersionSelected.value = unitVersionSelected.value.filter(id => id !== item.version_id)
  }
}

function viewUnitVersionDetail(item) {
  unitVersionDetail.value = item
  unitVersionDetailModalOpen.value = true
}

async function onActivateUnitVersion(item) {
  try {
    await mdmApi.activateUnitVersion(unitVersionDrawerUnitCode.value, item.version_id)
    message.success(`已激活版本 ${item.version_number}`)
    await loadUnitVersions()
    await loadTableData()
  } catch (e) {
    console.error('激活版本失败:', e)
    message.error('激活版本失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function openUnitCompareDrawer() {
  if (unitVersionSelected.value.length !== 2) return
  unitCompareLoading.value = true
  unitCompareDrawerOpen.value = true
  unitCompareResult.value = null
  try {
    const [v1, v2] = unitVersionSelected.value
    const data = await mdmApi.compareUnitVersions(unitVersionDrawerUnitCode.value, v1, v2)
    unitCompareResult.value = data
  } catch (e) {
    console.error('版本对比失败:', e)
    message.error('版本对比失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    unitCompareLoading.value = false
  }
}

function formatSnapshotValue(val) {
  if (val === null || val === undefined || val === '') return '—'
  if (typeof val === 'boolean') return val ? '是' : '否'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function diffTagColor(changeType) {
  switch (changeType) {
    case 'added': return 'green'
    case 'removed': return 'red'
    case 'modified': return 'orange'
    default: return 'default'
  }
}

function diffTagText(changeType) {
  switch (changeType) {
    case 'added': return '新增'
    case 'removed': return '删除'
    case 'modified': return '修改'
    default: return '未变'
  }
}

// 暴露 iconMap 给模板
window._iconMap = iconMap
</script>

<style scoped>
.mdm-center {
  padding: 16px 24px;
}

.page-header {
  margin-bottom: 16px;
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

.mdm-body {
  min-height: calc(100vh - 140px);
}

.tree-card, .table-card {
  height: calc(100vh - 140px);
  overflow: hidden;
}

.tree-card :deep(.ant-card-body),
.table-card :deep(.ant-card-body) {
  height: calc(100% - 40px);
  overflow: auto;
}

.mdm-tree {
  font-size: 13px;
}

.card-title {
  font-size: 14px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.text-ellipsis {
  display: inline-block;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
</style>

<!-- 非scoped：版本对比差异行高亮（Drawer teleport 到 body，scoped 无法穿透）-->
<style>
.version-diff-row td {
  padding: 6px 8px !important;
}
.version-diff-modified td {
  background-color: #fffbe6 !important;
}
.version-diff-added td {
  background-color: #f6ffed !important;
}
.version-diff-removed td {
  background-color: #fff1f0 !important;
}
</style>
