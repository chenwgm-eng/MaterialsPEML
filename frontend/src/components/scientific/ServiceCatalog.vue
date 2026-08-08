<template>
  <div class="service-catalog">
    <div v-for="phase in phases" :key="phase.id" class="phase-group">
      <div class="phase-header">
        <span class="phase-tag">Phase {{ phase.id }}</span>
        <span class="phase-name">{{ phase.name }}</span>
      </div>
      <div class="phase-cards">
        <div
          v-for="svc in phase.services"
          :key="svc.id"
          class="service-card"
          :class="{ active: selectedId === svc.id }"
          @click="$emit('select', svc)"
        >
          <div class="service-card-head">
            <span class="service-name">{{ svc.name }}</span>
            <span class="service-cap" :title="svc.capabilityId">{{ svc.capabilityId }}</span>
          </div>
          <p class="service-desc">{{ svc.description }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  selectedId: { type: String, default: '' },
})

defineEmits(['select'])

// 12 个原生科学服务，按 Phase 0-3 分组
// capabilityId 与后端服务注册的 capability_id 一致
const phases = [
  {
    id: 0,
    name: '基础性质',
    services: [
      { id: 'mpa', capabilityId: 'mpa', name: '分子性质预测', description: '预测 42 种分子物化性质与不确定性' },
      { id: 'chemical', capabilityId: 'chem_properties', name: '化学性质查询', description: 'M1-M5 模块：常数、相平衡、闪蒸、溶解度' },
      { id: 'structure', capabilityId: 'materials_structure', name: '材料结构生成', description: 'SMILES/Formula/CIF 互转与几何优化' },
    ],
  },
  {
    id: 1,
    name: '建模仿真',
    services: [
      { id: 'formulation', capabilityId: 'formulation_packing', name: '配方与堆积', description: '配方比例优化与分子堆积结构生成' },
      { id: 'molecular_simulation', capabilityId: 'molecular_simulation', name: '分子动力学', description: 'OpenMM/LAMMPS 多系综 MD 模拟与轨迹分析' },
    ],
  },
  {
    id: 2,
    name: '反应合成',
    services: [
      { id: 'synthesis_planning', capabilityId: 'synthesis_planning', name: '合成路线规划', description: 'RDKit 逆合成分析与文献验证' },
      { id: 'reaction_network', capabilityId: 'reaction_network', name: '反应网络分析', description: '反应枚举、过渡态搜索、网络扩展' },
      { id: 'molecular_docking', capabilityId: 'molecular_docking', name: '分子对接', description: 'AutoDock Vina 单次/批量对接与位姿分析' },
    ],
  },
  {
    id: 3,
    name: '过程分析',
    services: [
      { id: 'process_modeling', capabilityId: 'process_modeling', name: '化工过程建模', description: 'M1-M6 模块：精馏、反应器、传热传质' },
      { id: 'wavefunction_analysis', capabilityId: 'wavefunction_analysis', name: '波函数分析', description: 'PySCF ESP/轨道分析与渲染' },
      { id: 'fluid_simulation', capabilityId: 'fluid_simulation', name: '流体模拟', description: 'FluidSim 求解器 NS 方程与参数扫描' },
    ],
  },
]
</script>

<style scoped>
.service-catalog {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}
.phase-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}
.phase-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 0 var(--space-xs);
}
.phase-tag {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  color: #fff;
  background: var(--primary);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  line-height: 1.5;
}
.phase-name {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  font-weight: var(--font-weight-medium);
}
.phase-cards {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-xs);
}
.service-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-card);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.service-card:hover {
  border-color: var(--primary-border);
  background: var(--primary-bg);
}
.service-card.active {
  border-color: var(--primary);
  background: var(--primary-bg);
  box-shadow: inset 3px 0 0 var(--primary);
}
.service-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: 2px;
}
.service-name {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}
.service-cap {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  font-family: 'SFMono-Regular', Consolas, monospace;
  background: var(--light-bg-hover);
  padding: 0 4px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.service-card.active .service-cap {
  color: var(--primary);
  background: var(--primary-bg);
}
.service-desc {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}
</style>
