<template>
  <a-card class="control-card" :bordered="false">
    <a-form layout="vertical">
      <a-row :gutter="16">
        <a-col :xs="24" :sm="12" :md="6">
          <a-form-item label="目标">
            <a-input v-model:value="form.target" placeholder="例如 LiCoO2" />
            <div class="template-chips">
              <span class="chip-label">模板：</span>
              <a-tag
                v-for="t in targetTemplates"
                :key="t"
                class="template-chip"
                @click="form.target = t"
              >
                {{ t }}
              </a-tag>
            </div>
          </a-form-item>
        </a-col>
        <a-col :xs="24" :sm="12" :md="6">
          <a-form-item label="目标属性">
            <a-select v-model:value="form.target_property" :options="propertyOptions" style="width: 100%" />
            <div class="template-chips">
              <a-radio-group v-model:value="form.optimize_mode" size="small" style="margin-top: 4px" @change="onOptimizeModeChange">
                <a-radio-button value="single">单目标</a-radio-button>
                <a-radio-button value="multi">多目标</a-radio-button>
              </a-radio-group>
            </div>
          </a-form-item>
        </a-col>
        <a-col :xs="24" :sm="12" :md="6">
          <a-form-item label="迭代次数">
            <a-input-number v-model:value="form.max_iterations" :min="1" :max="10" :parser="iterParser" :formatter="iterFormatter" style="width: 100%" />
          </a-form-item>
        </a-col>
        <a-col :xs="24" :sm="12" :md="6">
          <a-form-item label=" ">
            <a-space v-if="running || cancelled" direction="vertical" style="width: 100%">
              <a-button v-if="cancelled" type="primary" @click="emit('run-again')" block>
                <PlayCircleOutlined /> 再次运行
              </a-button>
              <a-button v-else danger :loading="running" @click="emit('cancel')" block>
                <CloseCircleOutlined /> 取消运行
              </a-button>
            </a-space>
            <a-button v-else type="primary" :disabled="!prerequisitesMet" @click="emit('run')" block>
              <PlayCircleOutlined /> 启动循环
            </a-button>
          </a-form-item>
        </a-col>
      </a-row>

      <!-- 多目标优化编辑器 -->
      <div v-if="form.optimize_mode === 'multi'" class="multi-objective-editor">
        <a-form-item label="多目标属性集" style="margin-bottom: 8px">
          <a-select
            v-model:value="form.multi_objective_props"
            mode="multiple"
            placeholder="选择多个目标属性"
            :options="multiObjectiveOptions"
            style="width: 100%"
          />
          <span class="input-hint">支持多目标帕累托加权优化，权重自动归一化</span>
        </a-form-item>
        <div v-if="form.multi_objective_props.length > 0" class="mo-grid" :class="{ 'mo-no-weights': hideObjectiveWeights }">
          <div class="mo-header">
            <span class="mo-col-prop">属性</span>
            <span v-if="!hideObjectiveWeights" class="mo-col-weight">权重</span>
            <span class="mo-col-dir">方向</span>
            <span class="mo-col-min">最小约束</span>
            <span class="mo-col-max">最大约束</span>
          </div>
          <div v-for="prop in form.multi_objective_props" :key="prop" class="mo-row">
            <span class="mo-col-prop">{{ multiObjectiveLabel(prop) }}</span>
            <span v-if="!hideObjectiveWeights" class="mo-col-weight">
              <a-input-number v-model:value="multiObjectiveConfig[prop].weight" :min="0" :max="1" :step="0.1" size="small" style="width: 80px" />
            </span>
            <span class="mo-col-dir">
              <a-select v-model:value="multiObjectiveConfig[prop].direction" size="small" style="width: 100px">
                <a-select-option value="maximize">最大化</a-select-option>
                <a-select-option value="minimize">最小化</a-select-option>
              </a-select>
            </span>
            <span class="mo-col-min">
              <a-input-number v-model:value="multiObjectiveConfig[prop].min" size="small" style="width: 100px" placeholder="无" />
            </span>
            <span class="mo-col-max">
              <a-input-number v-model:value="multiObjectiveConfig[prop].max" size="small" style="width: 100px" placeholder="无" />
            </span>
          </div>
        </div>
        <a-alert v-if="hideObjectiveWeights" type="info" show-icon message="已切换 EHVI（超体积改进）策略：权重字段自动隐藏，优化基于帕累托前沿而非加权求和" style="margin-top: 8px" />
      </div>
    </a-form>
  </a-card>
</template>

<script setup>
import { PlayCircleOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  // 父组件传入的 reactive form 对象（按引用修改，避免大量 v-model 透传）
  form: { type: Object, required: true },
  propertyOptions: { type: Array, default: () => [] },
  running: { type: Boolean, default: false },
  cancelled: { type: Boolean, default: false },
  prerequisitesMet: { type: Boolean, default: false },
  // 多目标优化可选项（由父组件统一维护，避免重复定义）
  multiObjectiveOptions: { type: Array, default: () => [] },
  // 多目标配置对象（reactive，父组件持有，子组件直接绑定嵌套属性）
  multiObjectiveConfig: { type: Object, required: true },
  // EHVI 策略下隐藏权重字段（超体积改进基于帕累托前沿，权重无效）
  hideObjectiveWeights: { type: Boolean, default: false },
})

const emit = defineEmits(['run', 'cancel', 'run-again'])

// 模板列表
const targetTemplates = ['LiCoO2', 'LiFePO4', 'polymer electrolyte PEO']

function multiObjectiveLabel(key) {
  const opt = props.multiObjectiveOptions.find((o) => o.value === key)
  return opt ? opt.label : key
}

// 单/多目标切换：显式同步 form.optimize_mode
function onOptimizeModeChange(e) {
  const val = e?.target?.value
  if (val) props.form.optimize_mode = val
}

// 迭代次数输入校验
function iterParser(value) {
  const cleaned = String(value).replace(/[^\d]/g, '')
  const n = parseInt(cleaned, 10)
  if (isNaN(n) || n < 1) return ''
  if (n > 10) return '10'
  return String(n)
}
function iterFormatter(value) {
  const n = Number(value)
  return isNaN(n) ? '' : String(n)
}
</script>

<style scoped>
.template-chips {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.chip-label {
  font-size: 12px;
  color: var(--text-muted);
}

.template-chip {
  cursor: pointer;
  margin: 0;
  transition: border-color var(--transition), color var(--transition), background var(--transition);
}

.template-chip:hover {
  border-color: var(--primary-border);
  color: var(--primary);
  background: var(--primary-bg);
}

.input-hint {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-muted);
}

/* 多目标优化编辑器 */
.multi-objective-editor {
  margin-top: 8px;
  padding: 12px 14px;
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: 8px;
}

.multi-objective-editor .mo-grid .mo-header,
.multi-objective-editor .mo-grid .mo-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1.2fr 1fr 1fr;
  align-items: center;
  gap: 8px;
}

.multi-objective-editor .mo-grid.mo-no-weights .mo-header,
.multi-objective-editor .mo-grid.mo-no-weights .mo-row {
  grid-template-columns: 1.4fr 1.2fr 1fr 1fr;
}

.multi-objective-editor .mo-grid .mo-header {
  padding: 4px 0;
  border-bottom: 1px solid var(--border, #e8e8e8);
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #5a5a5a);
}

.multi-objective-editor .mo-grid .mo-row {
  padding: 6px 0;
  font-size: 13px;
  color: var(--text-primary, #1a1a2e);
}

.multi-objective-editor .mo-grid .mo-col-prop {
  font-weight: 500;
}
</style>
