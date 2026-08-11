<template>
  <div class="goal-intent-input">
    <a-textarea
      :value="modelValue"
      :rows="rows"
      :placeholder="placeholder"
      class="goal-textarea"
      @input="onInput"
      @keydown.enter.prevent="onParse"
    />
    <div class="goal-actions">
      <div class="goal-templates">
        <span class="tpl-label">场景模板：</span>
        <a-tag
          v-for="t in templates"
          :key="t.text"
          class="tpl-tag"
          role="button"
          tabindex="0"
          @click="applyTemplate(t)"
        >{{ t.name }}</a-tag>
      </div>
      <a-button type="primary" size="small" :loading="parsing" @click="onParse">
        <template #icon><BulbOutlined /></template>
        智能解析
      </a-button>
    </div>

    <!-- 解析结果预览：体系/属性/约束 chips，一键应用到表单 -->
    <div v-if="parsedResult" class="parse-result">
      <div class="parse-head">
        <span class="parse-title">已识别：</span>
        <a-tag v-if="parsedResult.material_system" color="blue">{{ parsedResult.material_system }}</a-tag>
        <a-tag v-if="parsedResult.material_scope" color="geekblue">
          {{ parsedResult.material_scope === 'polymer' ? '高分子' : parsedResult.material_scope === 'crystal' ? '晶体' : '分子' }}
        </a-tag>
        <a-tag
          v-for="tp in parsedResult.target_properties"
          :key="tp.name"
          color="cyan"
        >{{ propLabel(tp.name) }}{{ constraintText(tp) }}</a-tag>
        <span v-if="!parsedResult.material_system && !parsedResult.target_properties.length" class="parse-none">未识别到体系与属性（可手动选择）</span>
      </div>
      <a-button
        v-if="hasRecognized"
        size="small"
        type="primary"
        ghost
        @click="applyParsed"
      >应用到表单</a-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { BulbOutlined } from '@ant-design/icons-vue'
import { parseGoal } from '@/api/goal'
import { message } from 'ant-design-vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '一句话描述研发目标，例如：开发冲击强度 ≥ 8 kJ/m² 的玻纤增强 PA6 改性料' },
  rows: { type: Number, default: 3 },
})

const emit = defineEmits(['update:modelValue', 'parsed'])

const parsing = ref(false)
const parsedResult = ref(null)

// 场景模板：点击即填充目标文本（学习成本 ≈ 0 的快捷入口）
const templates = [
  { name: 'PA6 玻纤增强', text: '开发拉伸强度 ≥ 160 MPa 的玻纤增强 PA6 改性料，用于汽车结构件' },
  { name: 'PC 阻燃', text: '设计阻燃等级 V-0 的 PC 材料，热变形温度 ≥ 130°C' },
  { name: 'ABS 增韧', text: '开发冲击强度 ≥ 20 kJ/m² 的增韧 ABS，保持刚性' },
  { name: 'PP 汽车件', text: '开发耐候高流动 PP，熔体流动速率 ≥ 20 g/10min' },
  { name: 'PBAT 降解', text: '设计生物降解 PBAT 共混材料，断裂伸长率 ≥ 300%' },
]

const _PROP_CN = {
  tensile_strength: '拉伸强度', flexural_modulus: '弯曲模量', impact_strength: '冲击强度',
  heat_deflection_temp: '热变形温度', melt_flow_index: '熔体流动速率',
  elongation_at_break: '断裂伸长率', thermal_stability: '热稳定温度',
  crystallinity: '结晶度', glass_transition_temp: '玻璃化转变温度',
}

function propLabel(key) {
  return _PROP_CN[key] || key
}

function constraintText(tp) {
  const dir = tp.direction === 'minimize' ? '↓' : '↑'
  if (tp.min != null && tp.max != null) return `${dir} [${tp.min}, ${tp.max}]`
  if (tp.min != null) return `${dir} ≥ ${tp.min}`
  if (tp.max != null) return `${dir} ≤ ${tp.max}`
  return dir
}

const hasRecognized = computed(() => {
  const r = parsedResult.value
  return !!(r && (r.material_system || r.target_properties?.length))
})

function onInput(e) {
  emit('update:modelValue', e.target.value)
  parsedResult.value = null
}

function applyTemplate(t) {
  emit('update:modelValue', t.text)
  parsedResult.value = null
}

async function onParse() {
  const goal = (props.modelValue || '').trim()
  if (!goal) {
    message.warning('请先输入研发目标')
    return
  }
  parsing.value = true
  try {
    const res = await parseGoal(goal)
    parsedResult.value = res
  } catch (e) {
    message.error(e?.response?.data?.detail || '解析失败，请重试')
  } finally {
    parsing.value = false
  }
}

function applyParsed() {
  emit('parsed', parsedResult.value)
  message.success('已应用解析结果')
}
</script>

<style scoped>
.goal-intent-input {
  width: 100%;
}
.goal-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
  flex-wrap: wrap;
  gap: 6px;
}
.goal-templates {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.tpl-label {
  color: #64748b;
  font-size: 12px;
}
.tpl-tag {
  cursor: pointer;
  background: #f1f5f9;
  border: 1px dashed #cbd5e1;
}
.tpl-tag:hover {
  border-color: #1d4ed8;
  color: #1d4ed8;
}
.parse-result {
  margin-top: 8px;
  padding: 8px 10px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.parse-title {
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}
.parse-none {
  color: #94a3b8;
  font-size: 12px;
}
</style>
