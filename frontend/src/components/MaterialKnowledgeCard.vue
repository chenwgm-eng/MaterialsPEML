<template>
  <a-card :bordered="false" class="related-knowledge-card" size="small">
    <template #title>
      <span class="card-title"><BulbOutlined /> 相关知识</span>
    </template>
    <template #extra>
      <router-link to="/knowledge-base" class="more-link">查看全部</router-link>
    </template>

    <a-spin :spinning="loading">
      <EmptyState
        v-if="!materials.length"
        type="data"
        description="暂无相关知识"
      />
      <div v-else class="knowledge-list">
        <div
          v-for="m in materials"
          :key="m.material_id"
          class="knowledge-item"
          @click="onSelect(m)"
        >
          <div class="knowledge-name">{{ m.canonical_name }}</div>
          <div class="knowledge-meta">
            <a-tag size="small" :color="tierColor(m.source_tier)">{{ tierLabel(m.source_tier) }}</a-tag>
            <span class="meta-text">{{ m.paper_count }} 文献 · {{ m.claim_count }} 主张</span>
          </div>
        </div>
      </div>
    </a-spin>
  </a-card>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { BulbOutlined } from '@ant-design/icons-vue'
import { listMaterials } from '@/api/knowledge'
import EmptyState from '@/components/EmptyState.vue'

const props = defineProps({
  /** 用于检索的关键词（通常是材料名、分子式等） */
  query: { type: String, default: '' },
  /** 最多展示多少条 */
  limit: { type: Number, default: 5 },
})

const emit = defineEmits(['select'])

const materials = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await listMaterials({ query: props.query, limit: props.limit })
    materials.value = data.materials || []
  } catch {
    materials.value = []
  } finally {
    loading.value = false
  }
}

function onSelect(m) {
  emit('select', m)
}

function tierLabel(tier) {
  const map = {
    database: '数据库',
    top_journal: '顶刊',
    journal: '期刊',
    preprint: '预印本',
    internal: '内部',
    llm_generated: 'LLM',
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

watch(() => props.query, load)
onMounted(load)
</script>

<style scoped>
.related-knowledge-card { border-radius: 8px; }
.card-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
}
.more-link { font-size: 12px; }

.knowledge-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.knowledge-item {
  padding: 8px 10px;
  border-radius: 6px;
  background: #fafbfc;
  cursor: pointer;
  transition: background 0.2s;
}

.knowledge-item:hover { background: #f0f5ff; }

.knowledge-name {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 4px;
}

.knowledge-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #8a92a6;
}
.meta-text { flex: 1; }
</style>
