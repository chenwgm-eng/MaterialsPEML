<template>
  <div class="candidate-table-wrap">
    <a-table
      :row-key="(record) => record._rowKey"
      :columns="columns"
      :data-source="tableData"
      :loading="loading"
      :pagination="{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }"
      :row-selection="rowSelection"
      size="small"
      class="candidate-table"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'formula'">
          <ChemicalFormula :formula="record.formula || ''" size="small" />
        </template>
        <template v-else-if="column.key === 'molecule'">
          <StructureView
            :smiles="record.smiles || record.monomer_smiles?.[0] || record.psmiles || ''"
            :formula="record.formula || ''"
            :space-group="record.space_group || ''"
            :structure-type="record.structure_type || ''"
            :kind="props.type === 'polymer' ? 'molecule' : 'crystal'"
            :size="120"
          />
        </template>
        <template v-else-if="column.key === 'mo_score'">
          <span class="mo-score-cell">
            <template v-if="record.multi_objective_score != null">{{ (record.multi_objective_score * 100).toFixed(1) }}%</template>
            <template v-else>-</template>
          </span>
        </template>
        <template v-else-if="column.key === 'mo_status'">
          <span class="mo-status-tags">
            <a-tag
              v-for="obj in props.moObjectives"
              :key="obj.key"
              :color="getMoStatus(record, obj) ? 'green' : 'red'"
              class="mo-status-tag"
            >
              {{ obj.name }} {{ getMoStatus(record, obj) ? '达标' : '不达标' }}
            </a-tag>
          </span>
        </template>
        <template v-else-if="column.key === 'committee_verdict'">
          <StatusBadge
            v-if="record.committee_verdict"
            :status="committeeDecisionToBadge(record.committee_verdict)"
            :label="committeeDecisionLabel(record.committee_verdict)"
          />
          <span v-else class="text-muted">-</span>
        </template>
        <template v-else-if="column.key === 'evidence_coverage'">
          <span v-if="record.evidence_coverage != null">{{ (record.evidence_coverage * 100).toFixed(0) }}%</span>
          <span v-else class="text-muted">-</span>
        </template>
        <template v-else-if="column.key === 'source'">
          <a-tag
            v-if="getSourceBadge(record).label !== '未知'"
            :color="getSourceBadge(record).color"
          >
            {{ getSourceBadge(record).label }}
          </a-tag>
          <span v-else class="text-muted">-</span>
        </template>
      </template>
      <template #emptyText>
        <a-empty :description="MESSAGES.empty + '，请执行材料发现'" />
      </template>
    </a-table>
  </div>
</template>

<script setup>
import { computed, h, onMounted } from 'vue'
import StructureView from './StructureView.vue'
import ScientificNotation from './ScientificNotation.vue'
import { getSourceBadge } from '@/utils/candidateSource'
import { useUnitSymbols } from '@/utils/mdmDict'
import { MESSAGES } from '@/constants/glossary'

const { symbols: unitSymbols, load: loadUnitSymbols } = useUnitSymbols()
const condUnit = computed(() => unitSymbols.value.conductivity || 'S/cm')
const energyUnit = computed(() => unitSymbols.value.energy || 'eV')
const energyPerAtomUnit = computed(() => unitSymbols.value.energy_per_atom || 'eV/atom')

onMounted(() => {
  loadUnitSymbols()
})

const props = defineProps({
  data: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  type: { type: String, default: 'crystal' },
  selectable: { type: Boolean, default: false },
  selected: { type: Array, default: () => [] },
  moObjectives: { type: Array, default: () => [] },
})

const emit = defineEmits(['select'])

// 为每条记录注入稳定的唯一行 key，避免相同 formula/smiles 导致选中异常
const tableData = computed(() =>
  props.data.map((record, index) => {
    const baseKey =
      record.id ||
      record.material_id ||
      record.candidate_id ||
      record.formula ||
      record.smiles ||
      record.name
    return {
      ...record,
      _rowKey: baseKey ? `${baseKey}-${index}` : `row-${index}`,
    }
  })
)

const columns = computed(() => {
  // 检测是否存在多目标评分列（任意一行有非空 multi_objective_score 即显示；0 是合法评分）
  const hasMultiScore = props.data.some(
    (r) => r.multi_objective_score !== undefined && r.multi_objective_score !== null
  )

  if (props.type === 'polymer') {
    const cols = [
      { title: '结构', key: 'molecule', width: 140, fixed: 'left' },
      { title: '名称', dataIndex: 'name', key: 'name', width: 200, ellipsis: true },
      { title: 'SMILES', dataIndex: 'smiles', key: 'smiles', ellipsis: true },
      { title: 'PSMILES', dataIndex: 'psmiles', key: 'psmiles', ellipsis: true },
      { title: '来源', dataIndex: 'source', key: 'source', width: 100, ellipsis: true },
      { title: '拉伸强度 (MPa)', dataIndex: 'tensile_strength', key: 'tensile_strength', width: 120, align: 'right', className: 'num-cell' },
      { title: '弯曲模量 (MPa)', dataIndex: 'flexural_modulus', key: 'flexural_modulus', width: 130, align: 'right', className: 'num-cell' },
      { title: '冲击强度 (kJ/m²)', dataIndex: 'impact_strength', key: 'impact_strength', width: 130, align: 'right', className: 'num-cell' },
      { title: '热变形温度 (°C)', dataIndex: 'heat_deflection_temp', key: 'heat_deflection_temp', width: 130, align: 'right', className: 'num-cell' },
    ]
    if (hasMultiScore) {
      cols.push({ title: '综合评分', dataIndex: 'multi_objective_score', key: 'mo_score', width: 110, align: 'right', className: 'num-cell' })
    }
    if (props.moObjectives.length > 0) {
      cols.push({ title: '达标状态', key: 'mo_status', width: props.moObjectives.length * 70 })
    }
    const hasCommitteeVerdict = props.data.some(r => r.committee_verdict !== undefined && r.committee_verdict !== null)
    if (hasCommitteeVerdict) {
      cols.push({ title: '委员会结论', key: 'committee_verdict', width: 130, align: 'center' })
    }
    const hasEvidenceCoverage = props.data.some(r => r.evidence_coverage !== undefined && r.evidence_coverage !== null)
    if (hasEvidenceCoverage) {
      cols.push({ title: '证据覆盖', key: 'evidence_coverage', width: 100, align: 'center' })
    }
    return cols
  }
  const cols = [
    { title: '结构', key: 'molecule', width: 140, fixed: 'left' },
    { title: '化学式', dataIndex: 'formula', key: 'formula', width: 140, fixed: 'left', ellipsis: true },
    { title: '结构类型', dataIndex: 'structure_type', key: 'structure_type', width: 120, ellipsis: true },
    { title: '空间群', dataIndex: 'space_group', key: 'space_group', width: 100 },
    { title: `带隙 (${energyUnit.value})`, dataIndex: 'band_gap', key: 'band_gap', width: 100, align: 'right', className: 'num-cell', customRender: ({ text }) => h(ScientificNotation, { value: text, precision: 4 }) },
    { title: `形成能 (${energyPerAtomUnit.value})`, dataIndex: 'formation_energy', key: 'formation_energy', width: 140, align: 'right', className: 'num-cell', customRender: ({ text }) => h(ScientificNotation, { value: text, precision: 4 }) },
    { title: `离子电导率 (${condUnit.value})`, dataIndex: 'ionic_conductivity_estimate', key: 'cond', width: 160, align: 'right', className: 'num-cell', customRender: ({ text }) => h(ScientificNotation, { value: text, property: 'ionic_conductivity_estimate' }) },
    { title: '稳定性', dataIndex: 'stability_score', key: 'stability', width: 100, align: 'right', className: 'num-cell', customRender: ({ text }) => h(ScientificNotation, { value: text, precision: 3 }) },
    { title: '来源', dataIndex: 'source', key: 'source', width: 120, ellipsis: true },
  ]
  if (hasMultiScore) {
    cols.push({ title: '综合评分', dataIndex: 'multi_objective_score', key: 'mo_score', width: 110, align: 'right', className: 'num-cell' })
  }
  if (props.moObjectives.length > 0) {
    cols.push({ title: '达标状态', key: 'mo_status', width: props.moObjectives.length * 70 })
  }
  const hasCommitteeVerdict = props.data.some(r => r.committee_verdict !== undefined && r.committee_verdict !== null)
  if (hasCommitteeVerdict) {
    cols.push({ title: '委员会结论', key: 'committee_verdict', width: 130, align: 'center' })
  }
  const hasEvidenceCoverage = props.data.some(r => r.evidence_coverage !== undefined && r.evidence_coverage !== null)
  if (hasEvidenceCoverage) {
    cols.push({ title: '证据覆盖', key: 'evidence_coverage', width: 100, align: 'center' })
  }
  return cols
})

const rowSelection = computed(() => {
  if (!props.selectable) return null
  return {
    selectedRowKeys: props.selected,
    onChange: (keys, rows) => {
      const cleaned = rows.map(({ _rowKey, ...rest }) => rest)
      emit('select', cleaned, keys)
    },
  }
})

function getMoStatus(record, obj) {
  const val = record[obj.key]
  if (val == null) return true
  if (obj.min != null && val < obj.min) return false
  if (obj.max != null && val > obj.max) return false
  return true
}

function committeeDecisionToBadge(decision) {
  const map = {
    pass: 'success',
    reject: 'failed',
    request_evidence: 'warning',
    human_review: 'warning',
    failed: 'failed',
  }
  return map[decision] || 'default'
}

function committeeDecisionLabel(decision) {
  const map = {
    pass: '通过',
    reject: '拒绝',
    request_evidence: '补证据',
    human_review: '人工复核',
  }
  return map[decision] || '待定'
}
</script>

<style scoped>
.candidate-table-wrap {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.candidate-table :deep(.ant-table) {
  border-radius: 0;
}

.candidate-table :deep(.ant-table-thead > tr > th) {
  background: var(--light-bg-hover) !important;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  padding: 8px 12px;
}

.candidate-table :deep(.ant-table-tbody > tr > td) {
  font-size: 13px;
  padding: 6px 12px;
}

.candidate-table :deep(.num-cell) {
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
  color: var(--text-primary);
}

.mo-score-cell {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--primary-bg, #e6f4ff);
  color: var(--primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.mo-status-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.mo-status-tag {
  margin: 0;
  font-size: 11px;
  line-height: 18px;
}

.candidate-table :deep(.ant-table-pagination) {
  margin: 12px 12px 8px !important;
}
</style>
