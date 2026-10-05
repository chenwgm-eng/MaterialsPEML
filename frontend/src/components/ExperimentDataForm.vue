<template>
  <a-form layout="vertical" size="small">
    <a-alert
      v-if="order"
      :message="`任务 ${order.order_id} · ${order.project_id || '无项目'} · 模式 ${executionModeLabel}`"
      type="info"
      show-icon
      style="margin-bottom: 12px"
    />
    <a-alert
      v-if="order?.execution_mode === 'AUTO_DEVICE'"
      message="自动设备模式：请在设备完成测量后，将读数录入下方表单；或在「物料规格库 → 设备配置」中配置设备 API 自动推送。"
      type="warning"
      show-icon
      style="margin-bottom: 12px"
    />
    <a-alert
      v-else-if="order?.execution_mode === 'EXTERNAL_LIMS' || order?.execution_mode === 'EXTERNAL_ELN'"
      message="外部系统模式：建议通过 LIMS/ELN API 推送结果。下方表单可用于补录或人工修正。"
      type="warning"
      show-icon
      style="margin-bottom: 12px"
    />

    <!-- 实验类型选择 -->
    <a-divider orientation="left" plain style="margin-top: 0">实验类型</a-divider>
    <a-form-item label="实验类型" required>
      <a-select
        v-model:value="experimentType"
        placeholder="选择实验类型以加载对应字段模板"
        show-search
        :loading="loadingTemplate"
        @change="onExperimentTypeChange"
      >
        <a-select-option
          v-for="t in templateTypes"
          :key="t.value"
          :value="t.value"
        >{{ t.label }}</a-select-option>
      </a-select>
    </a-form-item>

    <!-- 警告提示 -->
    <a-alert
      v-if="warnings.length > 0"
      type="warning"
      show-icon
      closable
      style="margin-bottom: 12px"
    >
      <template #message>
        <span>数据合理性提醒：</span>
        <ul style="margin: 4px 0 0 16px; padding: 0">
          <li v-for="w in warnings" :key="w">{{ w }}</li>
        </ul>
      </template>
    </a-alert>

    <!-- 样品信息（元数据字段） -->
    <a-divider orientation="left" plain>样品信息</a-divider>
    <a-row :gutter="12">
      <a-col :span="8">
        <a-form-item label="样品 ID" required>
          <a-input v-model:value="formData.sample_id" placeholder="如：SMP_001" />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item label="批次 ID">
          <a-input v-model:value="formData.sample_batch_id" placeholder="批次号" />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item label="录入人">
          <a-input v-model:value="formData.uploaded_by" placeholder="操作员" />
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 测量属性（动态模板字段） -->
    <a-divider orientation="left" plain>测量属性</a-divider>
    <EmptyState
      v-if="!experimentType"
      type="data"
      description="请先选择实验类型"
      style="padding: 12px 0"
    />
    <a-spin v-else-if="loadingTemplate" style="display: block; padding: 12px 0" />
    <template v-else>
      <a-row :gutter="12" v-for="(row, rowIdx) in fieldRows" :key="rowIdx" style="margin-bottom: 8px">
        <a-col
          v-for="(field, colIdx) in row"
          :key="field.key"
          :span="fieldColSpan(field)"
        >
          <a-form-item
            :label="field.label_cn"
            :required="field.required"
          >
            <!-- 数值型字段（支持科学计数法，如 1.2e-3） -->
            <a-input
              v-if="field.value_type === 'float' || field.value_type === 'int'"
              v-model:value="templateValues[field.key]"
              style="width: 100%"
              :placeholder="resolvedUnit(field) ? `单位: ${resolvedUnit(field)}（支持科学计数法，如 1.2e-3）` : '请输入数值（支持科学计数法，如 1.2e-3）'"
              @change="onNumericFieldChange(field); onFieldChange()"
            >
              <template v-if="resolvedUnit(field)" #addonAfter>{{ resolvedUnit(field) }}</template>
            </a-input>
            <!-- 文本型字段（有选项） -->
            <a-select
              v-else-if="field.value_type === 'str' && field.options && field.options.length > 0"
              v-model:value="templateValues[field.key]"
              :placeholder="'请选择' + field.label_cn"
              allow-clear
              show-search
            >
              <a-select-option
                v-for="opt in field.options"
                :key="opt"
                :value="opt"
              >{{ opt }}</a-select-option>
            </a-select>
            <!-- 文本型字段（无选项） -->
            <a-input
              v-else-if="field.value_type === 'str'"
              v-model:value="templateValues[field.key]"
              :placeholder="'请输入' + field.label_cn"
            />
            <!-- 文件型字段 -->
            <a-upload
              v-else-if="field.value_type === 'file'"
              :file-list="fileList"
              :before-upload="(f) => { handleFileUpload(f, field.key); return false }"
              :max-count="1"
              @remove="() => { fileList = []; templateValues[field.key] = '' }"
            >
              <a-button size="small">
                <UploadOutlined /> 上传文件
              </a-button>
            </a-upload>
            <!-- 其他类型 -->
            <a-input
              v-else
              v-model:value="templateValues[field.key]"
              :placeholder="'请输入' + field.label_cn"
            />
          </a-form-item>
        </a-col>
      </a-row>
    </template>

    <!-- 测试条件 -->
    <a-divider orientation="left" plain>测试条件</a-divider>
    <a-row :gutter="12">
      <a-col :span="6">
        <a-form-item :label="`温度 (${tempUnit})`">
          <a-input-number
            v-model:value="formData.test_conditions.temperature"
            style="width: 100%"
            :step="0.1"
            placeholder="25"
            @change="validateTemperature"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item label="循环次数">
          <a-input-number
            v-model:value="formData.test_conditions.cycle_count"
            style="width: 100%"
            :step="1"
            placeholder="100"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item :label="`频率 (${freqUnit})`">
          <a-input-number
            v-model:value="formData.test_conditions.frequency_Hz"
            style="width: 100%"
            :step="1"
            placeholder="1e6"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item label="气氛">
          <a-select v-model:value="formData.test_conditions.atmosphere" allow-clear placeholder="氩气">
            <a-select-option value="Ar">氩气</a-select-option>
            <a-select-option value="N2">氮气</a-select-option>
            <a-select-option value="Air">空气</a-select-option>
            <a-select-option value="Vacuum">真空</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 原始数据文件 -->
    <a-divider orientation="left" plain>原始数据文件</a-divider>
    <a-form-item label="原始数据 URI">
      <a-input v-model:value="formData.raw_file_uri" placeholder="如：s3://bucket/exp/SMP_001.csv 或本地路径" />
    </a-form-item>

    <!-- 数据质量分层 -->
    <a-divider orientation="left" plain>数据质量</a-divider>
    <a-form-item label="数据质量分层" required>
      <a-select
        v-model:value="formData.data_quality"
        placeholder="选择数据质量分层"
      >
        <a-select-option value="verified">实测（verified，经 QC 审核确认）</a-select-option>
        <a-select-option value="estimated">估算（estimated，基于经验或模型推算）</a-select-option>
        <a-select-option value="simulated">模拟（simulated，DFT/MD 等计算结果）</a-select-option>
        <a-select-option value="literature">文献（literature，引用已发表论文数据）</a-select-option>
      </a-select>
    </a-form-item>
  </a-form>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import { UploadOutlined } from '@ant-design/icons-vue'
import { getPropertyTemplate, listPropertyTemplates } from '@/api/properties'
import { useUnitSymbols, usePropertyUnits } from '@/utils/mdmDict'
import EmptyState from '@/components/EmptyState.vue'

const { symbols: unitSymbols, load: loadUnitSymbols } = useUnitSymbols()
const { load: loadPropertyUnits, getDefaultUnit: getPropertyDefaultUnit } = usePropertyUnits()
const tempUnit = computed(() => unitSymbols.value.temperature || '°C')
const freqUnit = computed(() => unitSymbols.value.frequency || 'Hz')
const condUnit = computed(() => unitSymbols.value.conductivity || 'S/cm')
const voltageUnit = computed(() => unitSymbols.value.voltage || 'V')

// 属性名→单位自动联动：优先取 MDM 特性主数据中该属性（field.key）的默认单位，
// 匹配不到则回退到模板自带的 field.unit
function resolvedUnit(field) {
  return getPropertyDefaultUnit(field.key) || field.unit || ''
}

const props = defineProps({
  order: { type: Object, default: null },
  formData: { type: Object, required: true },
})

// 实验类型
const experimentType = ref('')
const templateTypes = ref([])
const templateFields = ref([])
const loadingTemplate = ref(false)

// 动态模板字段值
const templateValues = reactive({})

// 文件上传
const fileList = ref([])

// 警告
const warnings = ref([])

// ======== 实验类型选项 ========
const EXPERIMENT_TYPE_LABELS = {
  tensile_strength: '拉伸强度',
  flexural_modulus: '弯曲模量',
  impact_strength: '冲击强度',
  melt_flow_index: '熔体流动速率',
  heat_deflection_temp: '热变形温度',
  xrd: 'X 射线衍射 (XRD)',
  sem: '扫描电镜 (SEM)',
  dsc: '差示扫描量热 (DSC)',
  tga: '热重分析 (TGA)',
}

const executionModeLabel = computed(() => {
  const map = {
    MANUAL_ENTRY: '人工录入',
    AUTO_DEVICE: '自动设备',
    EXTERNAL_LIMS: '外部 LIMS',
    EXTERNAL_ELN: '外部 ELN',
  }
  return map[props.order?.execution_mode] || '人工录入'
})

// 将模板字段按两列排列
const fieldRows = computed(() => {
  const rows = []
  const fields = templateFields.value
  for (let i = 0; i < fields.length; i += 2) {
    rows.push(fields.slice(i, i + 2))
  }
  return rows
})

function fieldColSpan(field) {
  // 单列时占满
  if (field.value_type === 'file') return 24
  const row = fieldRows.value.find(r => r.includes(field))
  if (row && row.length === 1) return 24
  return 12
}

// ======== 加载模板类型列表 ========
async function loadTemplateTypes() {
  try {
    const res = await listPropertyTemplates()
    const types = res.experiment_types || []
    templateTypes.value = types.map(t => ({
      value: t,
      label: EXPERIMENT_TYPE_LABELS[t] || t,
    }))
  } catch {
    // 兜底
    templateTypes.value = Object.keys(EXPERIMENT_TYPE_LABELS).map(k => ({
      value: k,
      label: EXPERIMENT_TYPE_LABELS[k],
    }))
  }
}

// ======== 选择实验类型后加载模板 ========
async function onExperimentTypeChange(type) {
  if (!type) {
    templateFields.value = []
    clearTemplateValues()
    return
  }
  loadingTemplate.value = true
  try {
    const res = await getPropertyTemplate(type)
    templateFields.value = res.fields || []
    // 初始化模板值
    clearTemplateValues()
    for (const f of templateFields.value) {
      if (f.value_type === 'float' || f.value_type === 'int') {
        templateValues[f.key] = null
      } else {
        templateValues[f.key] = ''
      }
    }
  } catch {
    templateFields.value = []
  } finally {
    loadingTemplate.value = false
  }
}

function clearTemplateValues() {
  for (const k of Object.keys(templateValues)) {
    delete templateValues[k]
  }
}

// 数值字段变更校验：非法数值（含科学计数法校验）清空并提示
function onNumericFieldChange(field) {
  const v = String(templateValues[field.key] ?? '').trim()
  if (v === '') return
  if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(v)) {
    message.warning(`「${field.label_cn || field.key}」不是合法数值，已清空`)
    templateValues[field.key] = null
  }
}

// ======== 数据合理性校验 ========
// 数值字段变更即触发全量范围校验（拉伸强度≤2000、冲击强度≤500 等 13 项白名单）
function onFieldChange() {
  validateAllFields()
}

function validateTemperature() {
  const t = props.formData.test_conditions?.temperature
  if (t !== null && t !== undefined && t !== '') {
    const num = Number(t)
    if (num < -50 || num > 500) {
      const msg = `温度 ${num} ${tempUnit.value} 超出常规范围 (-50 ~ 500 ${tempUnit.value})，请确认数据正确`
      if (!warnings.value.includes(msg)) {
        warnings.value.push(msg)
      }
    }
  }
}

function validateAllFields() {
  warnings.value = []
  // 数值范围校验表（与后端 _PROPERTY_VALUE_RANGES 白名单对齐；缺省仅 NaN 检查）
  const ranges = {
    tensile_strength: { max: 2000, unit: 'MPa', label: '拉伸强度' },
    tensile_modulus: { max: 50000, unit: 'MPa', label: '拉伸模量' },
    flexural_modulus: { max: 50000, unit: 'MPa', label: '弯曲模量' },
    flexural_strength: { max: 2000, unit: 'MPa', label: '弯曲强度' },
    impact_strength: { max: 500, unit: 'kJ/m²', label: '冲击强度' },
    heat_deflection_temp: { max: 500, unit: '°C', label: '热变形温度' },
    melt_flow_index: { max: 500, unit: 'g/10min', label: '熔体流动速率' },
    elongation_at_break: { max: 1500, unit: '%', label: '断裂伸长率' },
    melting_point: { max: 600, unit: '°C', label: '熔点' },
    thermal_stability: { max: 900, unit: '°C', label: '热稳定温度' },
    weight_loss: { max: 100, unit: '%', label: '失重率' },
    residual_mass: { max: 100, unit: '%', label: '残余质量' },
    crystallinity: { max: 100, unit: '%', label: '结晶度' },
  }
  for (const [key, cfg] of Object.entries(ranges)) {
    const v = templateValues[key]
    if (v === null || v === undefined || v === '') continue
    const num = Number(v)
    if (!Number.isFinite(num)) {
      warnings.value.push(`${cfg.label} 不是有效数值，请检查`)
      continue
    }
    if (num < 0) {
      warnings.value.push(`${cfg.label} 不应为负数，请检查数值`)
    } else if (num > cfg.max) {
      warnings.value.push(`${cfg.label} ${num} ${cfg.unit} 超出常规范围（通常 < ${cfg.max} ${cfg.unit}），请确认数据正确`)
    }
  }
  // 温度校验
  validateTemperature()
}

// 文件上传处理
function handleFileUpload(file, key) {
  fileList.value = [file]
  templateValues[key] = file.name
  return false
}

// 获取模板数据（供父组件调用）。数值字段用 Number() 解析支持科学计数法
function getTemplatePayload() {
  const payload = {}
  for (const f of templateFields.value) {
    const val = templateValues[f.key]
    if (val !== null && val !== undefined && val !== '') {
      if (f.value_type === 'float' || f.value_type === 'int') {
        const num = Number(val)
        if (isNaN(num)) {
          continue // 解析失败的字段不放入 payload，由父组件阻断提交
        }
        payload[f.key] = num
      } else {
        payload[f.key] = val
      }
    }
  }
  return payload
}

defineExpose({ getTemplatePayload, warnings, templateFields })

onMounted(() => {
  loadTemplateTypes()
  loadUnitSymbols()
  loadPropertyUnits()
  // 初始化 test_conditions
  if (!props.formData.test_conditions) {
    props.formData.test_conditions = {
      temperature: null,
      cycle_count: null,
      frequency_Hz: null,
      atmosphere: '',
    }
  }
})

// 当 order 变化时尝试自动匹配实验类型
// 修复：切换订单必须重置模板与值（抽屉 destroy-on-close=false 时组件不重建，
// 不重置会把上一订单的模板值带到新订单，录错模板）
watch(() => props.order, (newOrder) => {
  experimentType.value = ''
  // 清空 reactive 模板值（reactive 无 .value，用 delete 逐个清除）
  Object.keys(templateValues).forEach((k) => { delete templateValues[k] })
  if (newOrder?.required_results?.length > 0) {
    // 尝试从 required_results 推断实验类型
    const knownTypes = Object.keys(EXPERIMENT_TYPE_LABELS)
    const matched = newOrder.required_results.find(r => knownTypes.includes(r))
    if (matched) {
      experimentType.value = matched
      onExperimentTypeChange(matched)
    }
  }
}, { immediate: true })
</script>