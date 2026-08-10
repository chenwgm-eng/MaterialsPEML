<template>
  <div class="structure-view" :style="{ width: size + 'px', height: size + 'px' }">
    <!-- 分子结构（SMILES） -->
    <MoleculeView v-if="showMolecule" :smiles="smiles" :size="size" />

    <!-- 晶体结构（晶胞缩略图） -->
    <div
      v-else-if="showCrystal"
      class="crystal-wrap"
      role="button"
      tabindex="0"
      :aria-label="`查看 ${formula || spaceGroup} 的晶体结构详情`"
      @click="modalVisible = true"
      @keydown.enter.prevent="modalVisible = true"
      @keydown.space.prevent="modalVisible = true"
    >
      <CrystalCellSvg :system="system" :lattice="lattice" :elements="elements" :width="size - 24" />
      <div class="crystal-caption">{{ spaceGroup || structureType || '晶体结构' }}</div>
      <div class="crystal-hover-hint">点击查看详情</div>
    </div>

    <!-- 无结构数据：生成中加载态 -->
    <div v-else class="structure-pending">
      <a-spin size="small" />
      <span class="pending-text">结构生成中</span>
    </div>

    <!-- 晶体详情弹窗 -->
    <a-modal
      v-model:open="modalVisible"
      :title="`晶体结构 — ${formula || spaceGroup}`"
      width="520px"
      :footer="null"
    >
      <div class="crystal-detail">
        <div class="detail-svg">
          <CrystalCellSvg :system="system" :lattice="lattice" :elements="elements" :width="240" />
        </div>
        <a-descriptions size="small" :column="1" bordered class="detail-desc">
          <a-descriptions-item label="化学式">
            <ChemicalFormula v-if="formula" :formula="formula" size="small" />
            <span v-else>—</span>
          </a-descriptions-item>
          <a-descriptions-item label="空间群">{{ spaceGroup || '—' }}</a-descriptions-item>
          <a-descriptions-item label="晶系">{{ systemLabel }}</a-descriptions-item>
          <a-descriptions-item label="结构类型">{{ structureType || '—' }}</a-descriptions-item>
          <a-descriptions-item label="点阵类型">{{ latticeLabel }}</a-descriptions-item>
        </a-descriptions>
        <div v-if="elements.length" class="element-legend">
          <span v-for="el in elements" :key="el" class="legend-item">
            <i class="legend-dot" :style="{ background: elementColor(el) }"></i>{{ el }}
          </span>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import MoleculeView from './MoleculeView.vue'
import CrystalCellSvg from './CrystalCellSvg.vue'
import {
  elementColor,
  parseFormula,
  detectCrystalSystem,
  detectLatticeCentering,
  CRYSTAL_SYSTEM_LABELS,
} from '@/utils/crystal'

const props = defineProps({
  smiles: { type: String, default: '' },
  formula: { type: String, default: '' },
  spaceGroup: { type: String, default: '' },
  structureType: { type: String, default: '' },
  kind: { type: String, default: 'auto' }, // auto | molecule | crystal
  size: { type: Number, default: 120 },
})

const modalVisible = ref(false)

const hasSmiles = computed(() => !!props.smiles?.trim())
const hasCrystalData = computed(
  () =>
    !!props.spaceGroup?.trim() ||
    !!props.structureType?.trim() ||
    (props.kind === 'crystal' && !!props.formula?.trim())
)

const showMolecule = computed(() => hasSmiles.value)
const showCrystal = computed(() => !hasSmiles.value && hasCrystalData.value)

const system = computed(() => detectCrystalSystem(props.spaceGroup))
const lattice = computed(() => detectLatticeCentering(props.spaceGroup))
const elements = computed(() => parseFormula(props.formula))
const systemLabel = computed(() => CRYSTAL_SYSTEM_LABELS[system.value] || system.value)
const latticeLabel = computed(() => {
  const names = { P: '简单点阵 (P)', I: '体心点阵 (I)', F: '面心点阵 (F)', C: '底心点阵 (C)', A: '底心点阵 (A)', B: '底心点阵 (B)', R: '菱方点阵 (R)' }
  return names[lattice.value] || lattice.value
})
</script>

<style scoped>
.structure-view {
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto;
}

.crystal-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border-radius: var(--radius-md, 8px);
  background: #fafafa;
  cursor: pointer;
  overflow: hidden;
  transition: background 0.2s;
}

.crystal-wrap:hover {
  background: #f0f0f0;
}

.crystal-wrap:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}

.crystal-caption {
  font-size: 11px;
  color: var(--text-secondary, #666);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.crystal-hover-hint {
  position: absolute;
  bottom: 2px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  color: var(--text-muted);
  opacity: 0;
  transition: opacity 0.2s;
  pointer-events: none;
  white-space: nowrap;
}

.crystal-wrap:hover .crystal-hover-hint {
  opacity: 1;
}

.structure-pending {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  height: 100%;
  border-radius: var(--radius-md, 8px);
  background: #fafafa;
}

.pending-text {
  font-size: 11px;
  color: var(--text-muted, #999);
}

.crystal-detail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.detail-svg {
  background: #fafafa;
  border-radius: 8px;
  padding: 8px;
}

.detail-desc {
  width: 100%;
}

.element-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: center;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary, #555);
}

.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1px solid #fff;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.15);
}
</style>
