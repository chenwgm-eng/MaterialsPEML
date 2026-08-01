<template>
  <div class="user-management">
    <div class="page-header">
      <h1 class="page-title">用户管理</h1>
      <p class="page-subtitle">系统用户与角色权限管理 — 五级角色体系、项目级访问控制</p>
    </div>

    <!-- 汇总卡片 -->
    <div class="stat-row" v-if="users.length > 0">
      <div class="stat-item">
        <span class="stat-value">{{ users.length }}</span>
        <span class="stat-label">用户总数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ activeCount }}</span>
        <span class="stat-label">启用中</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ adminCount }}</span>
        <span class="stat-label">管理员</span>
      </div>
    </div>

    <!-- 用户表格 -->
    <a-card class="table-card" :bordered="false">
      <template #title>
        <div class="card-title-row">
          <span class="card-title-text">用户清单</span>
          <a-tag color="blue" class="count-tag">{{ users.length }} 人</a-tag>
        </div>
      </template>
      <template #extra>
        <a-space>
          <a-input
            v-model:value="searchKeyword"
            placeholder="搜索用户名 / 显示名 / 邮箱…"
            allow-clear
            size="small"
            style="width: 220px"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
          <a-select
            v-model:value="roleFilter"
            placeholder="角色筛选"
            allow-clear
            size="small"
            style="width: 150px"
            :options="roleOptions"
          />
          <a-tooltip title="新增用户将写入用户库，默认角色为只读访客">
            <a-button type="primary" size="small" @click="onAdd">
              <PlusOutlined /> 新增用户
            </a-button>
          </a-tooltip>
          <a-button size="small" :loading="loading" @click="fetchUsers">
            <ReloadOutlined /> 刷新
          </a-button>
        </a-space>
      </template>
      <a-table
        v-if="filteredUsers.length > 0 || loading"
        :data-source="filteredUsers"
        :loading="loading"
        :pagination="{ pageSize: 10, showTotal: (t) => `共 ${t} 人`, showSizeChanger: true, pageSizeOptions: ['10', '20', '50'] }"
        :columns="columns"
        size="middle"
        :row-key="(r) => r.user_id"
        :scroll="{ x: 1000 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'username'">
            <span class="user-name">{{ record.username }}</span>
          </template>
          <template v-else-if="column.key === 'role'">
            <a-tag :color="roleColor(record.role)">
              {{ roleLabel(record.role) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'is_active'">
            <a-tag :color="record.is_active ? 'green' : 'default'">
              {{ record.is_active ? '启用' : '禁用' }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'project_ids'">
            <template v-if="(record.project_ids || []).length === 0">
              <a-tag color="blue">全部项目</a-tag>
            </template>
            <template v-else>
              <a-tag v-for="pid in record.project_ids" :key="pid" style="margin: 2px">
                {{ projectName(pid) }}
              </a-tag>
            </template>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space size="small">
              <a-tooltip title="查看详情">
                <a-button size="small" type="link" @click="onDetail(record)">
                  <EyeOutlined /> 详情
                </a-button>
              </a-tooltip>
              <a-tooltip title="编辑用户">
                <a-button size="small" type="link" @click="onEdit(record)">
                  <EditOutlined /> 修改
                </a-button>
              </a-tooltip>
              <a-popconfirm
                v-if="record.is_active"
                title="确认禁用该用户？禁用后该用户将无法登录。"
                ok-text="确认禁用"
                cancel-text="取消"
                @confirm="onToggleStatus(record)"
              >
                <a-button size="small" type="link" danger>禁用</a-button>
              </a-popconfirm>
              <a-button
                v-else
                size="small"
                type="link"
                style="color: var(--success)"
                @click="onToggleStatus(record)"
              >
                启用
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>
      <div v-else class="empty-state">
        {{ searchKeyword.trim() || roleFilter ? '未找到匹配的用户，请调整搜索条件' : '暂无用户数据，请点击「新增用户」添加' }}
      </div>
    </a-card>

    <!-- 新增/编辑用户抽屉 -->
    <a-drawer
      :open="formModalVisible"
      :title="formMode === 'create' ? '新增用户' : `编辑用户 ${form.username}`"
      placement="right"
      width="640px"
      @update:open="(v) => (formModalVisible = v)"
    >
      <a-form ref="formRef" layout="vertical" size="small" :model="form" :rules="formRules">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="用户名" name="username" required>
              <a-input
                v-model:value="form.username"
                :disabled="formMode === 'edit'"
                placeholder="登录用户名…"
                autocomplete="off"
                :spellcheck="false"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="显示名">
              <a-input v-model:value="form.display_name" placeholder="如 张三…" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="邮箱" name="email">
              <a-input v-model:value="form.email" placeholder="user@example.com…" autocomplete="email" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="角色" name="role" required>
              <a-select v-model:value="form.role" :options="roleOptions" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="密码">
          <a-input-password
            v-model:value="form.password"
            :placeholder="formMode === 'edit' ? '留空则不修改密码…' : '请输入初始密码…'"
            autocomplete="new-password"
          />
        </a-form-item>
        <a-form-item label="可访问项目">
          <a-select
            v-model:value="form.project_ids"
            mode="multiple"
            :options="projectOptions"
            placeholder="留空表示可访问全部项目…"
            allow-clear
          />
        </a-form-item>
        <a-form-item label="状态">
          <a-switch
            v-model:checked="form.is_active"
            checked-children="启用"
            un-checked-children="禁用"
          />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="formSubmitting" @click="formModalVisible = false">取消</a-button>
          <a-button type="primary" :loading="formSubmitting" @click="onSubmitForm">保存</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 用户详情抽屉（只读） -->
    <a-drawer
      :open="detailVisible"
      :title="`用户详情 — ${detailUser?.username || ''}`"
      placement="right"
      width="640px"
      :footer="null"
      @update:open="(v) => (detailVisible = v)"
    >
      <a-descriptions v-if="detailUser" size="small" :column="1" bordered>
        <a-descriptions-item label="用户名">{{ detailUser.username }}</a-descriptions-item>
        <a-descriptions-item label="显示名">{{ detailUser.display_name || '-' }}</a-descriptions-item>
        <a-descriptions-item label="邮箱">{{ detailUser.email || '-' }}</a-descriptions-item>
        <a-descriptions-item label="角色">
          <a-tag :color="roleColor(detailUser.role)">{{ roleLabel(detailUser.role) }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="状态">
          <a-tag :color="detailUser.is_active ? 'green' : 'default'">
            {{ detailUser.is_active ? '启用' : '禁用' }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="可访问项目">
          <template v-if="(detailUser.project_ids || []).length === 0">
            <a-tag color="blue">全部项目</a-tag>
          </template>
          <template v-else>
            <a-tag v-for="pid in detailUser.project_ids" :key="pid" style="margin: 2px">
              {{ projectName(pid) }}
            </a-tag>
          </template>
        </a-descriptions-item>
      </a-descriptions>
      <EmptyState v-else type="data" description="暂无用户详情" />
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  PlusOutlined, ReloadOutlined, EditOutlined, EyeOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import { listUsers, createUser, updateUser } from '@/api/auth'
import client from '@/api/client'
import { message } from 'ant-design-vue'
import { useMdmDict } from '@/utils/mdmDict'
import { required, lengthRange, email } from '@/utils/formRules'
import { ROLE_LABEL_MAP } from '@/constants/roles'
import EmptyState from '@/components/EmptyState.vue'

const route = useRoute()
const router = useRouter()

const users = ref([])
const loading = ref(false)
const projects = ref([])
const searchKeyword = ref('')
const roleFilter = ref(undefined)

// 新增/编辑表单
const formModalVisible = ref(false)
const formSubmitting = ref(false)
const formMode = ref('create')
const emptyForm = () => ({
  user_id: '',
  username: '',
  display_name: '',
  email: '',
  role: 'viewer',
  password: '',
  project_ids: [],
  is_active: true,
})
const form = ref(emptyForm())

// P1-FORM-001：表单校验规则
const formRef = ref()
const formRules = {
  username: [...required('请输入用户名'), ...lengthRange(3, 50, '用户名长度需在 3-50 个字符之间')],
  email: [...required('请输入邮箱'), ...email()],
  phone: [
    {
      validator: (_rule, value) => {
        if (!value) return Promise.resolve()
        return /^1\d{10}$/.test(value) ? Promise.resolve() : Promise.reject('请输入正确的 11 位手机号')
      },
      trigger: 'blur',
    },
  ],
  role: required('请选择角色', 'change'),
  department: required('请选择部门'),
}

// 详情抽屉（只读）
const detailVisible = ref(false)
const detailUser = ref(null)

const ROLE_OPTIONS_DEFAULT = [
  'admin',
  'pm',
  'researcher',
  'reviewer',
  'data_engineer',
  'viewer',
].map((value) => ({ label: ROLE_LABEL_MAP[value], value }))
const roleOptions = ref([...ROLE_OPTIONS_DEFAULT])

const columns = [
  { title: '用户名', key: 'username', dataIndex: 'username', width: 120 },
  { title: '显示名', dataIndex: 'display_name', key: 'display_name', width: 120 },
  { title: '邮箱', dataIndex: 'email', key: 'email', width: 180 },
  { title: '角色', key: 'role', width: 100 },
  { title: '状态', key: 'is_active', width: 80 },
  { title: '项目权限', key: 'project_ids' },
  { title: '操作', key: 'actions', width: 220 },
]

const activeCount = computed(() => users.value.filter((u) => u.is_active).length)
const adminCount = computed(() => users.value.filter((u) => u.role === 'admin').length)

const filteredUsers = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  return users.value.filter((u) => {
    if (roleFilter.value && u.role !== roleFilter.value) return false
    if (!kw) return true
    return [u.username, u.display_name, u.email]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(kw))
  })
})

const projectOptions = computed(() =>
  projects.value.map((p) => ({ label: p.name || p.project_id, value: p.project_id })),
)

function roleColor(role) {
  const map = { admin: 'red', pm: 'orange', researcher: 'blue', reviewer: 'green', viewer: 'default' }
  return map[role] || 'default'
}

function roleLabel(role) {
  const opt = roleOptions.value.find((r) => r.value === role)
  if (opt) return opt.label
  const fallback = Object.fromEntries(ROLE_OPTIONS_DEFAULT.map((o) => [o.value, o.label]))
  return fallback[role] || role
}

async function loadMdmOptions() {
  const { dimensionOptions } = useMdmDict()
  const loaded = await dimensionOptions('role')
  if (loaded.length) {
    roleOptions.value = loaded
  } else {
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
}

function projectName(pid) {
  const p = projects.value.find((x) => x.project_id === pid)
  return p ? p.name || pid : pid
}

async function fetchUsers() {
  loading.value = true
  try {
    const data = await listUsers()
    users.value = Array.isArray(data) ? data : []
  } catch {
    // 错误由拦截器处理（如 403 提示权限不足）
    users.value = []
  } finally {
    loading.value = false
  }
}

async function fetchProjects() {
  try {
    const data = await client.get('/projects')
    projects.value = Array.isArray(data) ? data : []
  } catch {
    projects.value = []
  }
}

function onAdd() {
  formMode.value = 'create'
  form.value = emptyForm()
  formModalVisible.value = true
}

function onDetail(record) {
  detailUser.value = record
  detailVisible.value = true
}

function onEdit(record) {
  formMode.value = 'edit'
  form.value = { ...emptyForm(), ...record, password: '' }
  formModalVisible.value = true
}

async function onSubmitForm() {
  // P1-FORM-001：提交前触发前端表单校验
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  if (formMode.value === 'create' && !form.value.password) {
    message.warning('请填写初始密码')
    return
  }
  formSubmitting.value = true
  try {
    if (formMode.value === 'create') {
      await createUser(form.value)
      message.success('用户已新增')
    } else {
      const payload = { ...form.value }
      delete payload.user_id
      delete payload.username
      if (!payload.password) delete payload.password
      await updateUser(form.value.user_id, payload)
      message.success('用户已更新')
    }
    formModalVisible.value = false
    await fetchUsers()
  } catch {
    // 错误由拦截器处理
  } finally {
    formSubmitting.value = false
  }
}

async function onToggleStatus(record) {
  try {
    await updateUser(record.user_id, { is_active: !record.is_active })
    message.success(`已${record.is_active ? '禁用' : '启用'}用户 ${record.username}`)
    await fetchUsers()
  } catch {
    // 错误由拦截器处理
  }
}

// P0-003：顶部「新建 → 新增用户」携带 ?create=1，自动打开弹窗
watch(
  () => route.query.create,
  (val) => {
    if (val === '1' || val === 1) {
      onAdd()
      // 打开后清除 query，避免刷新重复触发
      router.replace({ path: '/users' })
    }
  },
  { immediate: true }
)

onMounted(async () => {
  await loadMdmOptions()
  fetchProjects()
  fetchUsers()
})
</script>

<style scoped>
.user-management {
  width: 100%;
  max-width: 100%;
  overflow-x: hidden;
}

.page-header {
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

.table-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  margin-bottom: 16px;
}

.stat-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.stat-item {
  flex: 1;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title-text {
  font-size: 14px;
  font-weight: 600;
}

.count-tag {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.user-name {
  font-family: monospace;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
}
</style>
