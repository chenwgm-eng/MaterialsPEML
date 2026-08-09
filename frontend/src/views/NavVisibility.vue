<template>
  <div class="nav-visibility-page page-shell">
    <!-- 顶部固定提示条（设计文档 4.E） -->
    <a-alert
      type="info"
      show-icon
      banner
      class="nav-visibility-tip"
      message="此设置仅影响导航是否显示，不影响该角色的实际数据权限"
    />

    <div v-if="state === 'forbidden'" class="empty-state">
      <a-result status="403" title="无管理权限" sub-title="不具备 user.manage 权限，无法管理导航可见性">
        <template #extra>
          <a-button type="primary" @click="$router.push('/')">返回首页</a-button>
        </template>
      </a-result>
    </div>

    <div v-else class="app-card">
      <div class="card-title-row">
        <span class="card-title-text">导航可见性矩阵</span>
        <div class="matrix-actions">
          <a-button @click="load" :disabled="saving || loading">刷新</a-button>
          <a-button type="primary" :loading="saving" @click="save">保存</a-button>
        </div>
      </div>

      <a-table
        :data-source="rows"
        :columns="columns"
        :pagination="false"
        size="middle"
        row-key="role"
        :loading="loading"
        class="nav-matrix-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'role'">
            <span class="role-cell">{{ roleLabel(record.role) }}</span>
          </template>
          <template v-else-if="ENTRY_KEYS.includes(column.key)">
            <a-switch
              :checked="!!getCell(record.role, column.key)"
              :checked-children="'显示'"
              :un-checked-children="'隐藏'"
              :aria-label="`${roleLabel(record.role)} ${ENTRY_LABELS[column.key]} 导航显示`"
              @change="(v) => setCell(record.role, column.key, !!v)"
            />
          </template>
        </template>
      </a-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useSystemStore } from '@/stores/system'
import { getNavVisibility, updateNavVisibility } from '@/api/navVisibility'
import { roleLabel } from '@/constants/roles'
import { message } from 'ant-design-vue'

const systemStore = useSystemStore()

const ENTRY_KEYS = ['workbench', 'project', 'capability', 'admin']

const ENTRY_LABELS = {
  workbench: '工作台',
  project: '项目',
  capability: '能力库',
  admin: '管理',
}

const ROLE_KEYS = ['admin', 'pm', 'researcher', 'reviewer', 'viewer', 'data_engineer']

const loading = ref(false)
const saving = ref(false)
// 'loading' | 'ok' | 'forbidden'：以后端是否返回全量 matrix 为准
const state = ref('loading')
const matrix = ref({}) // { role: { entry: bool } }

const columns = computed(() => [
  { title: '角色', key: 'role', width: 140, fixed: 'left' },
  ...ENTRY_KEYS.map((k) => ({ title: ENTRY_LABELS[k], key: k, align: 'center' })),
])

const rows = computed(() => ROLE_KEYS.map((role) => ({ role })))

function getCell(role, entry) {
  return matrix.value[role]?.[entry]
}

function setCell(role, entry, val) {
  if (!matrix.value[role]) matrix.value[role] = {}
  matrix.value[role][entry] = val
}

async function load() {
  loading.value = true
  try {
    const data = await getNavVisibility()
    if (data && data.matrix) {
      state.value = 'ok'
      matrix.value = data.matrix
    } else {
      // 普通角色拿不到 matrix：即使守卫放行也表现无权限
      state.value = 'forbidden'
      message.warning('当前账号无 user.manage 权限，无法管理导航可见性')
    }
  } catch {
    state.value = 'forbidden'
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await updateNavVisibility({ matrix: matrix.value })
    message.success('导航可见性已保存')
    await load()
    // B2 缓存失效信号：使 visibleEntries 缓存失效重拉
    await systemStore.fetchMe()
  } catch {
    // 错误由拦截器统一提示
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.nav-visibility-page {
  gap: var(--space-md);
}

.nav-visibility-tip {
  margin-bottom: 0;
}

.matrix-actions {
  display: inline-flex;
  gap: var(--space-sm);
}

.role-cell {
  font-weight: 600;
}

.nav-matrix-table :deep(.ant-table-cell) {
  vertical-align: middle;
}

/* —— 无障碍（T13）：键盘焦点可见 —— */
.matrix-actions :deep(.ant-btn:focus-visible),
.nav-matrix-table :deep(.ant-switch:focus-visible),
.nav-visibility-tip :deep(.ant-alert-close-icon:focus-visible) {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .nav-visibility-page *,
  .nav-visibility-page *::before,
  .nav-visibility-page *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
  }
}
</style>