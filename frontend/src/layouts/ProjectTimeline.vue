<template>
  <div class="project-timeline">
    <div class="panel-head">
      <span class="panel-title">最近动态</span>
    </div>

    <div v-if="loading" class="tl-loading"><a-spin size="small" /></div>

    <template v-else>
      <div v-if="visibleEvents.length" class="tl-list">
        <div v-for="(ev, idx) in visibleEvents" :key="`${ev.type}-${idx}`" class="tl-item" @click="go(ev)">
          <span class="tl-dot" :class="`ev-${ev.priority}`" />
          <div class="tl-body">
            <div class="tl-title" :title="ev.title">{{ ev.title }}</div>
            <div class="tl-meta">{{ ev.time }}</div>
          </div>
        </div>
      </div>
      <div v-else class="tl-empty">暂无相关动态</div>

      <div v-if="collapsedEvents.length" class="tl-more" @click="expanded = !expanded">
        <a-button type="link" size="small">{{ expanded ? '收起' : `更多 ${collapsedEvents.length} 条` }}</a-button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSystemStore } from '@/stores/system'
import { getEcmlRuns } from '@/api/ecml'
import { listProjectTasks } from '@/api/projects'

const props = defineProps({
  projectId: { type: String, default: '' },
})

const router = useRouter()
const systemStore = useSystemStore()

const rawEvents = ref([])
const loading = ref(false)
const expanded = ref(false)

const CRITICAL = new Set(['task_due', 'approval', 'review'])
const TECHNICAL = new Set(['ecml_step', 'ecml_rerun', 'log'])

const events = computed(() => {
  const list = [...rawEvents.value]
  // 关键 > 业务 > 技术；同优先级按时间倒序
  const rank = (e) => (CRITICAL.has(e.type) ? 0 : TECHNICAL.has(e.type) ? 2 : 1)
  return list
    .filter((e) => e.time)
    .sort((a, b) => {
      const r = rank(a) - rank(b)
      if (r !== 0) return r
      return new Date(b.time) - new Date(a.time)
    })
})

const visibleEvents = computed(() =>
  expanded.value ? events.value : events.value.filter((e) => rank(e) !== 2).slice(0, 5),
)

const collapsedEvents = computed(() => events.value.slice(visibleEvents.value.length))

function rank(e) {
  return CRITICAL.has(e.type) ? 0 : TECHNICAL.has(e.type) ? 2 : 1
}

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return d.toLocaleDateString('zh-CN')
}

async function load() {
  loading.value = true
  const out = []
  if (!props.projectId) {
    rawEvents.value = []
    loading.value = false
    return
  }
  try {
    // ECML 闭环运行
    try {
      const ecml = await getEcmlRuns(20, props.projectId)
      ;(ecml.runs || []).forEach((r) =>
        out.push({
          type: (r.status === 'timeout' || r.status === 'failed') ? 'ecml_rerun' : 'ecml_step',
          priority: 'business',
          title: `闭环迭代 ${r.target || r.run_id}`,
          time: r.updated_at,
          link: `/ecml?run_id=${encodeURIComponent(r.run_id)}`,
        }),
      )
    } catch {
      /* ignore */
    }
    // 项目任务状态变化
    try {
      const tasks = await listProjectTasks(props.projectId)
      const arr = Array.isArray(tasks) ? tasks : (tasks.tasks || [])
      arr.forEach((t) =>
        out.push({
          type: t.status === 'done' || t.status === 'completed' ? 'task_done' : 'task_change',
          priority: 'business',
          title: `任务「${t.title}」`,
          time: t.updated_at || t.created_at,
          link: `/my-tasks?task_id=${encodeURIComponent(t.task_id)}`,
        }),
      )
    } catch {
      /* ignore */
    }
  } finally {
    rawEvents.value = out
    loading.value = false
  }
}

function go(ev) {
  if (ev.link) router.push(ev.link)
}

watch(() => props.projectId, load)
onMounted(load)
</script>

<style scoped>
.project-timeline {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 0;
  border-top: 1px solid var(--border);
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--sidebar-text);
}
.tl-loading {
  padding: 12px 0;
  text-align: center;
}
.tl-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tl-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.tl-item:hover {
  background: var(--surface-hover);
}
.tl-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 5px;
  flex-shrink: 0;
}
.ev-0 { background: var(--danger); }
.ev-1 { background: var(--primary); }
.ev-2 { background: var(--text-on-dark-muted); }
.tl-body {
  flex: 1;
  min-width: 0;
}
.tl-title {
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tl-meta {
  font-size: 11px;
  color: var(--text-muted);
}
.tl-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 4px;
}
.tl-more {
  text-align: center;
}
</style>