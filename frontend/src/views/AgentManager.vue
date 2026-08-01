<template>
  <div class="agent-manager-page">
    <div class="page-header page-header-row">
      <div>
        <h1 class="page-title">智能体管理</h1>
        <p class="page-subtitle">研发小队成员管理，支持自定义智能体</p>
      </div>
      <div class="header-actions">
        <a-button type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新建智能体
        </a-button>
      </div>
    </div>

    <a-card :bordered="false" class="tabs-card">
      <a-tabs v-model:activeKey="activeTab">
        <a-tab-pane key="builtin">
          <template #tab>
            内置智能体 <span class="tab-count">{{ builtinAgents.length }}</span>
          </template>
          <a-spin :spinning="loading">
            <EmptyState v-if="!loading && builtinAgents.length === 0" type="data" description="暂无内置智能体" />
            <a-table
              v-else
              :columns="agentColumns"
              :data-source="builtinAgents"
              :pagination="false"
              size="middle"
              row-key="id"
              :scroll="{ x: 1240 }"
              class="agent-table"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'name'">
                  <div class="name-cell">
                    <span class="name-text">{{ record.name }}</span>
                    <a-tag v-if="record.status === 'development'" class="status-tag status-dev">开发中</a-tag>
                  </div>
                </template>
                <template v-else-if="column.key === 'role'">
                  <span class="text-secondary">{{ roleLabel(record.role) }}</span>
                </template>
                <template v-else-if="column.key === 'capabilities'">
                  <a-tooltip v-if="record.capabilities?.length" :title="record.capabilities.map(capabilityLabel).join('、')">
                    <span class="text-muted">{{ record.capabilities.map(capabilityLabel).join('、') }}</span>
                  </a-tooltip>
                  <span v-else class="text-muted">—</span>
                </template>
                <template v-else-if="column.key === 'model'">
                  <div class="model-cell">
                    <div class="model-primary">{{ record.effective_model_primary || record.effective_model || record.llm_model || '—' }}</div>
                    <div v-if="record.effective_model_secondary" class="model-secondary">
                      备选：{{ record.effective_model_secondary }}
                    </div>
                  </div>
                </template>
                <template v-else-if="column.key === 'tools'">
                  <span class="text-muted">{{ record.tools?.length || 0 }}</span>
                </template>
                <template v-else-if="column.key === 'health'">
                  <a-tag :color="healthColor(agentHealthDisplay(record).health)" class="status-tag">
                    {{ healthLabel(agentHealthDisplay(record).health) }}
                  </a-tag>
                </template>
                <template v-else-if="column.key === 'stats'">
                  <span v-if="agentStats[record.id]" class="text-muted">
                    {{ agentStats[record.id].invocations }} 次
                    <span v-if="agentStats[record.id].success_rate !== null" class="text-secondary">
                      · {{ Math.round(agentStats[record.id].success_rate * 100) }}%
                    </span>
                  </span>
                  <span v-else class="text-muted">—</span>
                </template>
                <template v-else-if="column.key === 'actions'">
                  <a-button size="small" type="link" @click="openDetail(record.id)">详情</a-button>
                  <a-button size="small" type="link" @click="openEdit(record.id)">编辑</a-button>
                  <a-button size="small" type="link" @click="openChat(record.id)">测试</a-button>
                </template>
              </template>
            </a-table>
          </a-spin>
        </a-tab-pane>

        <a-tab-pane key="custom">
          <template #tab>
            自定义智能体 <span class="tab-count">{{ customAgents.length }}</span>
          </template>
          <a-spin :spinning="loading">
            <EmptyState v-if="!loading && customAgents.length === 0" type="create" description="暂无自定义智能体" action-text="新建智能体" @action="openCreate" />
            <a-table
              v-else
              :columns="agentColumns"
              :data-source="customAgents"
              :pagination="false"
              size="middle"
              row-key="id"
              :scroll="{ x: 1240 }"
              class="agent-table"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'name'">
                  <div class="name-cell">
                    <span class="name-text">{{ record.name }}</span>
                    <a-tag v-if="record.status === 'development'" class="status-tag status-dev">开发中</a-tag>
                  </div>
                </template>
                <template v-else-if="column.key === 'role'">
                  <span class="text-secondary">{{ roleLabel(record.role) }}</span>
                </template>
                <template v-else-if="column.key === 'capabilities'">
                  <a-tooltip v-if="record.capabilities?.length" :title="record.capabilities.map(capabilityLabel).join('、')">
                    <span class="text-muted">{{ record.capabilities.map(capabilityLabel).join('、') }}</span>
                  </a-tooltip>
                  <span v-else class="text-muted">—</span>
                </template>
                <template v-else-if="column.key === 'model'">
                  <div class="model-cell">
                    <div class="model-primary">{{ record.effective_model_primary || record.effective_model || record.llm_model || '—' }}</div>
                    <div v-if="record.effective_model_secondary" class="model-secondary">
                      备选：{{ record.effective_model_secondary }}
                    </div>
                  </div>
                </template>
                <template v-else-if="column.key === 'tools'">
                  <span class="text-muted">{{ record.tools?.length || 0 }}</span>
                </template>
                <template v-else-if="column.key === 'health'">
                  <a-tag :color="healthColor(agentHealthDisplay(record).health)" class="status-tag">
                    {{ healthLabel(agentHealthDisplay(record).health) }}
                  </a-tag>
                </template>
                <template v-else-if="column.key === 'stats'">
                  <span v-if="agentStats[record.id]" class="text-muted">
                    {{ agentStats[record.id].invocations }} 次
                    <span v-if="agentStats[record.id].success_rate !== null" class="text-secondary">
                      · {{ Math.round(agentStats[record.id].success_rate * 100) }}%
                    </span>
                  </span>
                  <span v-else class="text-muted">—</span>
                </template>
                <template v-else-if="column.key === 'actions'">
                  <a-button size="small" type="link" @click="openDetail(record.id)">详情</a-button>
                  <a-button size="small" type="link" @click="openEdit(record.id)">编辑</a-button>
                  <a-button size="small" type="link" @click="openChat(record.id)">测试</a-button>
                  <a-button size="small" type="link" danger @click="onDelete(record.id)">删除</a-button>
                </template>
              </template>
            </a-table>
          </a-spin>
        </a-tab-pane>

        <a-tab-pane key="routes">
          <template #tab>
            模型路由 <span class="tab-count">{{ modelRoutes.length }}</span>
            <a-tag color="orange" class="planned-tag">规划中</a-tag>
          </template>
          <a-alert
            type="info"
            show-icon
            class="routes-alert"
            message="该功能尚在规划中，当前配置暂未接入运行时"
          >
            <template #description>
              <div class="routes-desc">
                <p class="routes-desc-para">
                  <strong>当前状态：</strong>模型路由表为只读预览，配置项不会影响实际 LLM 调用。智能体当前实际使用各自配置的「优先/备选模型提供方」字段调用 LLM。
                </p>
                <p class="routes-desc-para">
                  <strong>未来运作方式：</strong>智能体执行任务时，系统将按其「能力契约 × 执行策略」（如 dft_verification × committee_governed）从此路由表匹配模型，自动决定调用哪个 Provider、模型 ID、温度与 Token 上限——无需为每个智能体单独配置模型。
                </p>
                <p class="routes-desc-para">
                  <strong>核心价值：</strong>将「能力」与「模型」解耦——同一能力（如 DFT 验证）在不同策略下可绑定不同模型（标准策略用经济模型，专家评审策略用大模型），实现按场景精细路由、成本与质量动态平衡、模型切换零代码改动。
                </p>
              </div>
            </template>
          </a-alert>
          <a-spin :spinning="routesLoading">
            <EmptyState v-if="!routesLoading && modelRoutes.length === 0" type="data" description="暂无模型路由" />
            <template v-else>
              <a-table
                :columns="routeColumns"
                :data-source="modelRoutes"
                :pagination="false"
                size="middle"
                row-key="route_id"
                :scroll="{ x: 980 }"
                class="agent-table"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'capability'">
                    <a-tooltip :title="record.capability">
                      <span>{{ capabilityLabel(record.capability) }}</span>
                    </a-tooltip>
                  </template>
                  <template v-if="column.key === 'profile'">
                    <a-tag class="status-tag">{{ record.profile }}</a-tag>
                  </template>
                  <template v-else-if="column.key === 'actions'">
                    <a-button size="small" type="link" @click="openRouteDetail(record)">详情</a-button>
                    <a-button v-if="isAdmin" size="small" type="link" @click="openEditRoute(record)">编辑</a-button>
                  </template>
                </template>
              </a-table>
            </template>
          </a-spin>
        </a-tab-pane>
      </a-tabs>
    </a-card>

    <!-- 新建 / 编辑 Agent 抽屉 -->
    <a-drawer
      :open="formVisible"
      :title="editingId ? '编辑智能体' : '新建智能体'"
      placement="right"
      width="600px"
      @update:open="(v) => (formVisible = v)"
    >
      <a-form layout="vertical" class="agent-form">
        <a-row :gutter="12">
          <a-col :span="6">
            <a-form-item label="头像">
              <a-input v-model:value="form.avatar" placeholder="留空将使用名称首字母" :maxlength="4" />
            </a-form-item>
          </a-col>
          <a-col :span="18">
            <a-form-item label="名称" required>
              <a-input v-model:value="form.name" placeholder="Agent 名称" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="角色" required>
              <a-select v-model:value="form.role" :options="roleOptions" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="优先模型提供方">
              <a-select
                v-model:value="form.provider"
                :options="providerOptions"
                placeholder="自动（按 llm_model 判断）"
                allow-clear
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item v-if="selectedProviderInfo" label="优先提供方 · 服务地址 / 模型">
          <a-input :value="selectedProviderInfo" disabled />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="备选模型提供方">
              <a-select
                v-model:value="form.provider_secondary"
                :options="providerOptionsWithNone"
                placeholder="无（优先模型失败时不切换）"
                allow-clear
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item v-if="selectedSecondaryInfo" label="备选提供方 · 服务地址 / 模型">
          <a-input :value="selectedSecondaryInfo" disabled />
        </a-form-item>
        <div class="form-hint">优先模型调用失败时，自动切换到备选模型重试</div>
        <a-form-item label="描述" tooltip="智能体职责的一句话说明，会拼入 AI 人设">
          <a-textarea v-model:value="form.description" :rows="2" placeholder="Agent 职责描述" />
        </a-form-item>
        <a-form-item label="擅长领域" tooltip="仅用于 AI 人设描述，不影响实际工具调用。输入标签后回车确认">
          <a-select
            v-model:value="form.expertise"
            mode="tags"
            placeholder="输入擅长领域标签后回车"
            :token-separators="[',']"
          />
        </a-form-item>
        <a-form-item label="可调用工具" tooltip="白名单：智能体执行任务时只能调用此处选中的工具，未选中的工具不可调用">
          <a-select
            v-model:value="form.tools"
            mode="multiple"
            placeholder="选择该智能体允许调用的工具"
            :options="toolOptions"
          />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="submitting" @click="formVisible = false">取消</a-button>
          <a-button type="primary" :loading="submitting" @click="onSubmit">保存</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- Agent 详情 Drawer -->
    <a-drawer
      :open="detailVisible"
      :width="780"
      title="智能体详情"
      placement="right"
      @update:open="(v) => (detailVisible = v)"
    >
      <a-spin :spinning="eligibilityLoading">
        <div v-if="currentAgent" class="detail-content">
          <!-- 基础信息 -->
          <div class="detail-section">
            <div class="detail-section-title">
              基础信息
              <span class="section-hint">智能体的身份与人设信息</span>
            </div>
            <a-descriptions size="small" :column="2" bordered>
              <a-descriptions-item label="头像">
                <span v-if="currentAgent.avatar">{{ currentAgent.avatar }}</span>
                <span v-else class="avatar-fallback">{{ currentAgent.name?.charAt(0) || '—' }}</span>
              </a-descriptions-item>
              <a-descriptions-item label="名称">{{ currentAgent.name }}</a-descriptions-item>
              <a-descriptions-item label="角色">{{ roleLabel(currentAgent.role) }}</a-descriptions-item>
              <a-descriptions-item label="优先模型">{{ currentAgent.effective_model_primary || currentAgent.effective_model || currentAgent.llm_model || '—' }}</a-descriptions-item>
            <a-descriptions-item label="备选模型">{{ currentAgent.effective_model_secondary || '无' }}</a-descriptions-item>
              <a-descriptions-item label="状态">{{ currentAgent.status || '—' }}</a-descriptions-item>
              <a-descriptions-item label="健康状态">
                <a-tag :color="healthColor(agentHealthDisplay(currentAgent).health)" class="status-tag">
                  {{ healthLabel(agentHealthDisplay(currentAgent).health) }}
                </a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="专长" :span="2">
                <div v-if="currentAgent.expertise?.length" class="tag-list">
                  <a-tag v-for="e in currentAgent.expertise" :key="e" class="status-tag">{{ e }}</a-tag>
                </div>
                <span v-else class="text-muted">—</span>
              </a-descriptions-item>
              <a-descriptions-item label="描述" :span="2">{{ currentAgent.description || '—' }}</a-descriptions-item>
            </a-descriptions>
          </div>

          <!-- 运行约束 -->
          <div class="detail-section">
            <div class="detail-section-title">
              运行约束
              <span class="section-hint">控制智能体执行任务时能做什么、不能做什么</span>
            </div>
            <a-descriptions size="small" :column="1" bordered>
              <a-descriptions-item label="能力契约">
                <div v-if="detailCapabilities.length" class="tag-list">
                  <a-tag v-for="c in detailCapabilities" :key="c" class="status-tag">{{ c }}</a-tag>
                </div>
                <span v-else class="text-muted">—</span>
              </a-descriptions-item>
              <a-descriptions-item label="允许策略">
                <div v-if="detailProfiles.length" class="tag-list">
                  <a-tag v-for="p in detailProfiles" :key="p" class="status-tag">{{ p }}</a-tag>
                </div>
                <span v-else class="text-muted">—</span>
              </a-descriptions-item>
              <a-descriptions-item label="自主等级">
                <span v-if="detailAutonomy" class="text-secondary">{{ detailAutonomy }}</span>
                <span v-else class="text-muted">—</span>
              </a-descriptions-item>
              <a-descriptions-item label="禁止动作">
                <div v-if="detailProhibited.length" class="tag-list">
                  <a-tag v-for="a in detailProhibited" :key="a" color="red" class="status-tag">{{ a }}</a-tag>
                </div>
                <span v-else class="text-muted">—</span>
              </a-descriptions-item>
            </a-descriptions>
          </div>

          <!-- 工具路由策略（全局，默认折叠） -->
          <a-collapse :bordered="false" class="eligibility-collapse">
            <a-collapse-panel key="eligibility">
              <template #header>
                <span class="detail-section-title collapse-title">
                  工具路由策略（全局）
                  <span class="section-hint">系统级策略，所有智能体共享；按能力维度配置工具绑定优先级与风险阈值</span>
                </span>
              </template>
              <EmptyState v-if="!eligibilityLoading && eligibilityRules.length === 0" type="data" description="暂无工具路由策略" />
              <a-table
                v-else
                :columns="eligibilityColumns"
                :data-source="eligibilityRules"
                :pagination="false"
                size="small"
                row-key="rule_id"
                :scroll="{ x: 680 }"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'capability'">
                    <a-tooltip :title="record.capability">
                      <span>{{ capabilityLabel(record.capability) }}</span>
                    </a-tooltip>
                  </template>
                  <template v-else-if="column.key === 'profiles'">
                    <a-tag v-for="p in record.profiles" :key="p" class="status-tag">{{ p }}</a-tag>
                  </template>
                  <template v-else-if="column.key === 'preferred_binding_order'">
                    <div class="binding-list">
                      <a-tag v-for="b in record.preferred_binding_order" :key="b" class="binding-tag">{{ b }}</a-tag>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'max_risk_level'">
                    <a-select
                      v-if="isAdmin"
                      :value="record.max_risk_level"
                      size="small"
                      style="width: 72px"
                      :options="riskLevelOptions"
                      @change="(v) => onRiskLevelChange(record, v)"
                    />
                    <a-tag v-else :color="riskColor(record.max_risk_level)" class="status-tag">{{ record.max_risk_level }}</a-tag>
                  </template>
                  <template v-else-if="column.key === 'requires_human_review'">
                    <a-tag v-if="record.requires_human_review" color="orange" class="status-tag">需人工</a-tag>
                    <span v-else class="text-muted">—</span>
                  </template>
                </template>
              </a-table>
            </a-collapse-panel>
          </a-collapse>
        </div>
        <EmptyState v-else-if="!eligibilityLoading" type="data" :description="MESSAGES.empty" />
      </a-spin>
    </a-drawer>

    <!-- 编辑模型路由抽屉 -->
    <a-drawer
      :open="routeFormVisible"
      title="编辑模型路由"
      placement="right"
      width="560px"
      @update:open="(v) => (routeFormVisible = v)"
    >
      <a-form layout="vertical" class="agent-form">
        <a-form-item label="路由 ID">
          <a-input :value="routeForm.route_id" disabled />
        </a-form-item>
        <a-form-item label="能力 / 策略">
          <a-input :value="`${routeForm.capability} / ${routeForm.profile}`" disabled />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="24">
            <a-form-item label="模型 ID">
              <a-input v-model:value="routeForm.model_id" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="最大 Token">
              <a-input-number v-model:value="routeForm.max_tokens" :min="1" :max="200000" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="温度">
              <a-input-number v-model:value="routeForm.temperature" :min="0" :max="2" :step="0.1" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="routeSubmitting" @click="routeFormVisible = false">取消</a-button>
          <a-button type="primary" :loading="routeSubmitting" @click="submitRouteEdit">保存</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 模型路由详情抽屉（只读） -->
    <a-drawer
      :open="routeDetailVisible"
      title="模型路由详情"
      placement="right"
      width="480px"
      @update:open="(v) => (routeDetailVisible = v)"
    >
      <a-descriptions v-if="routeDetail" size="small" :column="1" bordered>
        <a-descriptions-item label="路由 ID">{{ routeDetail.route_id }}</a-descriptions-item>
        <a-descriptions-item label="能力">
          {{ capabilityLabel(routeDetail.capability) }}
          <span class="text-muted" style="margin-left: 8px;">{{ routeDetail.capability }}</span>
        </a-descriptions-item>
        <a-descriptions-item label="策略">
          <a-tag class="status-tag">{{ routeDetail.profile }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="Provider">{{ routeDetail.provider_id || '—' }}</a-descriptions-item>
        <a-descriptions-item label="模型 ID">{{ routeDetail.model_id || '—' }}</a-descriptions-item>
        <a-descriptions-item label="最大 Token">{{ routeDetail.max_tokens ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="温度">{{ routeDetail.temperature ?? '—' }}</a-descriptions-item>
      </a-descriptions>
      <EmptyState v-else type="data" :description="MESSAGES.empty" />
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button @click="routeDetailVisible = false">关闭</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 测试对话抽屉 -->
    <a-drawer
      :open="chatVisible"
      :title="chatTitle"
      placement="right"
      width="640px"
      @update:open="(v) => (chatVisible = v)"
    >
      <div class="chat-container">
        <div class="chat-meta" v-if="chatAgentInfo">
          <div class="chat-meta-row">
            <span class="chat-meta-label">优先</span>
            <a-tag class="status-tag">{{ chatAgentInfo.provider_label }}</a-tag>
            <span class="text-muted">{{ chatAgentInfo.base_url }} · {{ chatAgentInfo.model }}</span>
          </div>
          <div v-if="chatAgentInfo.secondary" class="chat-meta-row">
            <span class="chat-meta-label">备选</span>
            <a-tag class="status-tag">{{ chatAgentInfo.secondary.provider_label }}</a-tag>
            <span class="text-muted">{{ chatAgentInfo.secondary.base_url }} · {{ chatAgentInfo.secondary.model }}</span>
          </div>
        </div>
        <div class="chat-messages" ref="chatMessagesRef">
          <div v-if="!chatHistory.length" class="chat-empty">
            输入消息与「{{ chatAgentInfo?.name || '智能体' }}」开始对话
          </div>
          <div
            v-for="(msg, idx) in chatHistory"
            :key="idx"
            class="chat-msg"
            :class="msg.role === 'user' ? 'chat-msg-user' : 'chat-msg-assistant'"
          >
            <div class="chat-msg-role">{{ msg.role === 'user' ? '我' : (chatAgentInfo?.name || 'AI') }}</div>
            <div class="chat-msg-content">{{ msg.content }}</div>
          </div>
          <div v-if="chatSending" class="chat-msg chat-msg-assistant">
            <div class="chat-msg-role">{{ chatAgentInfo?.name || 'AI' }}</div>
            <div class="chat-msg-content chat-typing">正在思考...</div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="chat-input-bar">
          <a-input
            v-model:value="chatInput"
            placeholder="输入消息，按 Enter 发送"
            :disabled="chatSending"
            @press-enter="sendChatMessage"
          />
          <a-button type="primary" :loading="chatSending" @click="sendChatMessage">发送</a-button>
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { listAgents, createAgent, updateAgent, deleteAgent, getAgentsHealth, getLlmOptions, chatWithAgent } from '@/api/agents'
import {
  getAgentEligibility,
  updateAgentEligibility,
  getModelRoutes,
  updateModelRoute,
} from '@/api/controlPlane'
import { getCapabilities } from '@/api/capabilities'
import { getAgentEventStats } from '@/api/agentEvents'
import { useMdmDict } from '@/utils/mdmDict'
import { useAuth } from '@/composables/useAuth'
import EmptyState from '@/components/EmptyState.vue'
import { MESSAGES } from '@/constants/glossary'

const { isAdmin } = useAuth()
const loading = ref(true)
const submitting = ref(false)
const agents = ref([])
const capabilityNameMap = ref(new Map())
const agentStats = ref({})
const agentHealth = ref({})
const activeTab = ref('builtin')
const formVisible = ref(false)
const editingId = ref(null)

const detailVisible = ref(false)
const currentAgentId = ref('')
const currentAgent = computed(() =>
  agents.value.find((a) => a.id === currentAgentId.value) || null,
)
const eligibilityRules = ref([])
const eligibilityLoading = ref(false)

const modelRoutes = ref([])
const routesLoading = ref(false)
const routeFormVisible = ref(false)
const routeSubmitting = ref(false)
const routeForm = reactive({
  route_id: '',
  capability: '',
  profile: '',
  model_id: '',
  max_tokens: 4096,
  temperature: 0.7,
})
const routeDetailVisible = ref(false)
const routeDetail = ref(null)

const form = reactive({
  name: '',
  role: 'material_discovery',
  description: '',
  expertise: [],
  tools: [],
  avatar: '',
  llm_model: 'LongCat-2.0',
  provider: '',
  provider_secondary: '',
  llm_model_secondary: '',
})

// 模型提供方选项（从后端 /agents/llm-options 加载）
const llmOptions = ref([])
const providerOptions = computed(() =>
  llmOptions.value.map((o) => ({
    label: `${o.label}${o.available ? '' : '（未配置）'}`,
    value: o.provider,
  })),
)
// 备选模型下拉选项：与优先模型相同，但额外多一个"无"选项（用 undefined 表示）
const providerOptionsWithNone = computed(() => providerOptions.value)

// 编辑抽屉中选中 provider 时展示对应的服务地址 + 模型名（只读）
const selectedProviderInfo = computed(() => {
  if (!form.provider) return ''
  const opt = llmOptions.value.find((o) => o.provider === form.provider)
  if (!opt) return ''
  return `${opt.base_url}  ·  ${opt.model}`
})

// 备选模型的服务地址 + 模型名（只读）
const selectedSecondaryInfo = computed(() => {
  if (!form.provider_secondary) return ''
  const opt = llmOptions.value.find((o) => o.provider === form.provider_secondary)
  if (!opt) return ''
  return `${opt.base_url}  ·  ${opt.model}`
})

// 测试对话抽屉
const chatVisible = ref(false)
const chatAgentId = ref('')
const chatAgentInfo = ref(null) // { name, provider_label, base_url, model }
const chatHistory = ref([]) // [{role, content}]
const chatInput = ref('')
const chatSending = ref(false)
const chatMessagesRef = ref(null)

const chatTitle = computed(() =>
  chatAgentInfo.value ? `测试对话 · ${chatAgentInfo.value.name}` : '测试对话',
)

const ROLE_OPTIONS_DEFAULT = [
  { label: '材料发现', value: 'material_discovery' },
  { label: '合成规划', value: 'synthesis_planning' },
  { label: 'DFT 验证', value: 'dft_verification' },
  { label: '实验分析', value: 'experiment_analysis' },
  { label: '项目经理', value: 'project_manager' },
  { label: '文献调研', value: 'literature_research' },
  { label: '质量审核', value: 'quality_review' },
  { label: '工业化配方验证', value: 'industrialization' },
  { label: '自定义', value: 'custom' },
]
const roleOptions = ref([...ROLE_OPTIONS_DEFAULT])

const toolOptions = [
  'generate_crystal_candidates',
  'generate_polymer_candidates',
  'predict_crystal_properties',
  'predict_polymer_properties',
  'check_synthesis_feasibility',
  'verify_dft',
  'get_experiment_results',
  'subscribe_experiment_updates',
  'route_material',
].map((t) => ({ label: t, value: t }))

const builtinAgents = computed(() => agents.value.filter((a) => a.is_builtin))
const customAgents = computed(() => agents.value.filter((a) => !a.is_builtin))

// 表格列定义
const agentColumns = [
  { title: '名称', key: 'name', width: 200, fixed: 'left' },
  { title: '角色', key: 'role', width: 110 },
  { title: '能力契约', key: 'capabilities', width: 200, ellipsis: true },
  { title: '模型', key: 'model', width: 140 },
  { title: '可调用工具', key: 'tools', width: 90, align: 'center' },
  { title: '健康状态', key: 'health', width: 110 },
  { title: '调用统计', key: 'stats', width: 130 },
  { title: '操作', key: 'actions', width: 240, fixed: 'right' },
]

const routeColumns = [
  { title: '能力', dataIndex: 'capability', key: 'capability', width: 200, ellipsis: true },
  { title: '策略', key: 'profile', width: 130 },
  { title: 'Provider', dataIndex: 'provider_id', key: 'provider_id', width: 100 },
  { title: '模型 ID', dataIndex: 'model_id', key: 'model_id', width: 200, ellipsis: true },
  { title: '最大 Token', dataIndex: 'max_tokens', key: 'max_tokens', width: 100 },
  { title: '温度', dataIndex: 'temperature', key: 'temperature', width: 100 },
  { title: '操作', key: 'actions', width: 120, fixed: 'right' },
]

const HEALTH_OPTIONS_DEFAULT = [
  { label: '正常', value: 'healthy' },
  { label: '降级', value: 'degraded' },
  { label: '未配置', value: 'unknown' },
  { label: '内置可用', value: 'builtin' },
]
const healthOptions = ref([...HEALTH_OPTIONS_DEFAULT])

function roleLabel(role) {
  const opt = roleOptions.value.find((r) => r.value === role)
  if (opt) return opt.label
  const fallback = Object.fromEntries(ROLE_OPTIONS_DEFAULT.map((o) => [o.value, o.label]))
  return fallback[role] || role || '—'
}

function healthColor(health) {
  const map = { healthy: 'green', degraded: 'orange', unknown: 'default', builtin: 'blue' }
  return map[health] || 'default'
}
function healthLabel(health) {
  const opt = healthOptions.value.find((h) => h.value === health)
  if (opt) return opt.label
  const fallback = Object.fromEntries(HEALTH_OPTIONS_DEFAULT.map((o) => [o.value, o.label]))
  return fallback[health] || '未配置'
}

function agentHealthDisplay(agent) {
  if (!agent) return { health: 'unknown', meta: '' }
  if (agent.is_builtin) {
    return { health: 'builtin', meta: '内置智能体 · 无需心跳上报' }
  }
  const h = agentHealth.value[agent.id]
  if (!h || h.last_heartbeat == null) {
    return { health: 'unknown', meta: '未配置心跳上报' }
  }
  return { health: h.health || 'unknown', meta: `${h.elapsed_seconds ?? '-'}s 前` }
}

const CAPABILITY_LABELS = {
  crystal_candidate_generation: '晶体候选生成',
  crystal_candidate_generation_v1: '晶体候选生成',
  polymer_candidate_generation: '聚合物候选生成',
  polymer_candidate_generation_v1: '聚合物候选生成',
  molecule_polymer_design: '分子/聚合物设计',
  crystal_property_prediction: '晶体性质预测',
  crystal_property_prediction_v1: '晶体性质预测',
  polymer_property_prediction: '聚合物性质预测',
  polymer_property_prediction_v1: '聚合物性质预测',
  property_prediction: '性质预测',
  cross_scale_prediction: '跨尺度预测',
  cross_scale_prediction_v1: '跨尺度预测',
  synthesis_planning: '合成路径规划',
  synthesis_planning_askcos: '逆合成规划（ASKCOS）',
  synthesis_planning_askcos_v1: '逆合成规划（ASKCOS）',
  synthesis_evidence: '合成证据评估',
  reaction_engineering_check: '反应工程检查',
  dft_verification: 'DFT 验证',
  dft_verification_v1: 'DFT 验证',
  experiment_analyst: '实验分析',
  experiment_analyst_v1: '实验分析智能体',
  experiment_qc_lookup: '实验质控查询',
  get_experiment_results: '获取实验结果',
  subscribe_experiment_updates: '订阅实验更新',
  literature_researcher: '文献调研',
  literature_researcher_v1: '文献调研智能体',
  evidence_research: '证据调研',
  material_knowledge_query: '材料知识查询',
  material_reference_lookup: '材料参考查询',
  material_planning: '材料规划',
  material_planner: '材料规划',
  committee_assessment: '委员会评估',
  committee_assessment_v1: '委员会评估',
  compliance_screening: '合规筛查',
  compliance_verifier: '合规验证',
  structure_validation: '结构验证',
  industrialization: '工业化验证',
  heuristic_baseline: '启发式基线',
  heuristic_baseline_v1: '启发式基线',
  ecml_closed_loop: 'ECML 闭环引擎',
  ecml_closed_loop_v1: 'ECML 闭环引擎',
  chemical_descriptors: '化学描述符计算',
  compound_registry_lookup: '化合物注册查询',
  bioactivity_risk_lookup: '生物活性风险查询',
  route_material: '材料路由',
  verify_dft: 'DFT 验证',
  generate_crystal_candidates: '生成晶体候选材料',
  generate_polymer_candidates: '生成聚合物候选材料',
  predict_crystal_properties: '预测晶体性质',
  predict_polymer_properties: '预测聚合物性质',
  check_synthesis_feasibility: '合成可行性检查',
}

const AUTONOMY_OPTIONS_DEFAULT = [
  { label: 'L0 · 仅建议（人工执行）', value: 'L0' },
  { label: 'L1 · 受监督执行（需人工确认）', value: 'L1' },
  { label: 'L2 · 自主执行（事后报备）', value: 'L2' },
  { label: 'L3 · 完全自主', value: 'L3' },
]
const autonomyOptions = ref([...AUTONOMY_OPTIONS_DEFAULT])

function capabilityLabel(cap) {
  if (!cap) return ''
  if (CAPABILITY_LABELS[cap]) return CAPABILITY_LABELS[cap]
  if (capabilityNameMap.value.has(cap)) return capabilityNameMap.value.get(cap)
  return cap
}

function autonomyLabel(level) {
  if (!level) return ''
  const opt = autonomyOptions.value.find((o) => o.value === level)
  if (opt) return opt.label
  const fallback = Object.fromEntries(AUTONOMY_OPTIONS_DEFAULT.map((o) => [o.value, o.label]))
  return fallback[level] || level
}

const PROHIBITED_ACTION_LABELS = {
  'experiment.start': '启动实验',
  'dft.submit': '提交 DFT 计算',
  'synthesis.execute': '执行合成',
  'formula.design': '配方设计',
  'compliance.verdict': '合规裁定',
}

function prohibitedLabel(action) {
  return PROHIBITED_ACTION_LABELS[action] || action
}

const detailCapabilities = computed(() => {
  const caps = currentAgent.value?.capabilities?.length
    ? currentAgent.value.capabilities
    : [...new Set(eligibilityRules.value.map((r) => r.capability))]
  return caps.map(capabilityLabel)
})
const detailProfiles = computed(() => {
  if (currentAgent.value?.allowed_profiles?.length) return currentAgent.value.allowed_profiles
  const set = new Set()
  eligibilityRules.value.forEach((r) => (r.profiles || []).forEach((p) => set.add(p)))
  return [...set]
})
const detailAutonomy = computed(() => autonomyLabel(currentAgent.value?.max_autonomy_level || ''))
const detailProhibited = computed(() =>
  (currentAgent.value?.prohibited_actions || []).map(prohibitedLabel)
)

const riskLevelOptions = ['A', 'B', 'C', 'D'].map((v) => ({ label: v, value: v }))
function riskColor(level) {
  return { A: 'green', B: 'blue', C: 'orange', D: 'red' }[level] || 'default'
}

const eligibilityColumns = [
  { title: '能力', dataIndex: 'capability', key: 'capability', width: 180, ellipsis: true },
  { title: '策略', key: 'profiles', width: 160 },
  { title: '绑定优先级', key: 'preferred_binding_order' },
  { title: '风险', key: 'max_risk_level', width: 90 },
  { title: '回退动作', dataIndex: 'fallback_action', key: 'fallback_action', width: 120, ellipsis: true },
  { title: '人工审核', key: 'requires_human_review', width: 80, align: 'center' },
]

function resetForm() {
  form.name = ''
  form.role = 'material_discovery'
  form.description = ''
  form.expertise = []
  form.tools = []
  form.avatar = ''
  form.llm_model = 'LongCat-2.0'
  form.provider = ''
  form.provider_secondary = ''
  form.llm_model_secondary = ''
  editingId.value = null
}

function openCreate() {
  resetForm()
  formVisible.value = true
}

function openEdit(id) {
  const agent = agents.value.find((a) => a.id === id)
  if (!agent) return
  editingId.value = id
  form.name = agent.name || ''
  form.role = agent.role || 'custom'
  form.description = agent.description || ''
  form.expertise = agent.expertise || []
  form.tools = agent.tools || []
  form.avatar = agent.avatar || ''
  form.llm_model = agent.llm_model || 'LongCat-2.0'
  form.provider = agent.provider || ''
  form.provider_secondary = agent.provider_secondary || ''
  form.llm_model_secondary = agent.llm_model_secondary || ''
  formVisible.value = true
}

// 加载模型提供方选项
async function loadLlmOptions() {
  try {
    const res = await getLlmOptions()
    llmOptions.value = res?.options || []
  } catch {
    llmOptions.value = []
  }
}

// 根据 provider/llm_model 计算展示信息
function resolveProviderInfo(provider, llmModel) {
  const p = (provider || '').toLowerCase()
  if (p === 'llm') {
    const opt = llmOptions.value.find((o) => o.provider === 'llm')
    return {
      provider_label: opt?.label || 'LLM 大模型',
      base_url: opt?.base_url || '',
      model: llmModel || opt?.model || '',
    }
  }
  if (p === 'internlm') {
    const opt = llmOptions.value.find((o) => o.provider === 'internlm')
    return {
      provider_label: opt?.label || 'AI 引擎',
      base_url: opt?.base_url || '',
      model: opt?.model || '',
    }
  }
  // 自动
  if (llmModel) {
    const opt = llmOptions.value.find((o) => o.provider === 'llm')
    return {
      provider_label: `自动 · ${opt?.label || 'LLM'}`,
      base_url: opt?.base_url || '',
      model: llmModel,
    }
  }
  const opt = llmOptions.value.find((o) => o.provider === 'internlm')
  return {
    provider_label: `自动 · ${opt?.label || 'InternLM'}`,
    base_url: opt?.base_url || '',
    model: opt?.model || '',
  }
}

// 打开测试对话抽屉
function openChat(id) {
  const agent = agents.value.find((a) => a.id === id)
  if (!agent) return
  chatAgentId.value = id
  chatHistory.value = []
  chatInput.value = ''
  chatSending.value = false

  const primary = resolveProviderInfo(agent.provider, agent.llm_model)
  const secondary = agent.provider_secondary
    ? resolveProviderInfo(agent.provider_secondary, agent.llm_model_secondary)
    : null

  chatAgentInfo.value = {
    name: agent.name,
    provider_label: primary.provider_label,
    base_url: primary.base_url,
    model: primary.model,
    secondary: secondary
      ? {
          provider_label: secondary.provider_label,
          base_url: secondary.base_url,
          model: secondary.model,
        }
      : null,
  }
  chatVisible.value = true
}

// 发送测试对话消息
async function sendChatMessage() {
  const text = chatInput.value.trim()
  if (!text || chatSending.value) return
  chatHistory.value.push({ role: 'user', content: text })
  chatInput.value = ''
  chatSending.value = true
  // 滚动到底部
  await nextTick()
  if (chatMessagesRef.value) {
    chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
  }
  try {
    const history = chatHistory.value
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .slice(0, -1) // 排除刚 push 的 user 消息（后端会拼接）
    const res = await chatWithAgent(chatAgentId.value, {
      message: text,
      history,
    })
    const reply = res?.reply || '（无回复）'
    chatHistory.value.push({ role: 'assistant', content: reply })
  } catch {
    /* handled by interceptor */
  } finally {
    chatSending.value = false
    await nextTick()
    if (chatMessagesRef.value) {
      chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
    }
  }
}

async function onSubmit() {
  if (!form.name.trim()) {
    message.warning('请填写 Agent 名称')
    return
  }
  submitting.value = true
  try {
    const payload = { ...form }
    // 根据 provider 同步 llm_model，保证存储一致：
    // - internlm：清空 llm_model（用 InternLM 模型）
    // - llm：llm_model 用 LLM 选项中的模型名
    // - 自动：保留现有 llm_model
    const normalize = (providerKey, llmModelKey) => {
      const p = (payload[providerKey] || '').toLowerCase()
      if (p === 'internlm') {
        payload[llmModelKey] = ''
      } else if (p === 'llm') {
        const opt = llmOptions.value.find((o) => o.provider === 'llm')
        payload[llmModelKey] = payload[llmModelKey] || opt?.model || 'LongCat-2.0'
      }
    }
    normalize('provider', 'llm_model')
    normalize('provider_secondary', 'llm_model_secondary')
    // 备选与优先相同则清空备选
    if (payload.provider_secondary && payload.provider_secondary === payload.provider) {
      payload.provider_secondary = ''
      payload.llm_model_secondary = ''
    }
    if (editingId.value) {
      await updateAgent(editingId.value, payload)
      message.success('Agent 已更新')
    } else {
      await createAgent(payload)
      message.success('Agent 已创建')
      // 新建自定义智能体后自动切换到「自定义智能体」标签页，方便用户立即查看结果
      activeTab.value = 'custom'
    }
    formVisible.value = false
    await loadAgents()
  } catch {
    /* handled by interceptor */
  } finally {
    submitting.value = false
  }
}

function onDelete(id) {
  const agent = agents.value.find((a) => a.id === id)
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除 Agent「${agent?.name || id}」吗？此操作不可撤销。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        await deleteAgent(id)
        message.success('Agent 已删除')
        await loadAgents()
      } catch {
        /* handled by interceptor */
      }
    },
  })
}

async function loadCapabilityNames() {
  try {
    const res = await getCapabilities()
    const contracts = res?.capabilities || res?.data || []
    const map = new Map()
    ;(Array.isArray(contracts) ? contracts : []).forEach((c) => {
      const id = c.capability_id || c.id
      const name = c.name
      if (id && name) map.set(id, name)
    })
    capabilityNameMap.value = map
  } catch {
    capabilityNameMap.value = new Map()
  }
}

async function loadAgents() {
  loading.value = true
  try {
    const res = await listAgents()
    agents.value = Array.isArray(res) ? res : (res?.agents || [])
  } catch {
    /* handled by interceptor */
  } finally {
    loading.value = false
  }
  try {
    const res = await getAgentEventStats()
    agentStats.value = res?.stats || {}
  } catch {
    agentStats.value = {}
  }
  try {
    const res = await getAgentsHealth()
    agentHealth.value = res?.health || {}
  } catch {
    agentHealth.value = {}
  }
}

async function openDetail(id) {
  currentAgentId.value = id
  detailVisible.value = true
  eligibilityRules.value = []
  eligibilityLoading.value = true
  try {
    const res = await getAgentEligibility(id)
    eligibilityRules.value = res?.rules || []
  } catch {
    /* handled by interceptor */
  } finally {
    eligibilityLoading.value = false
  }
}

async function onRiskLevelChange(rule, newLevel) {
  try {
    const updated = { ...rule, max_risk_level: newLevel }
    await updateAgentEligibility(currentAgentId.value, [updated])
    message.success('风险等级已更新')
    await openDetail(currentAgentId.value)
  } catch {
    /* handled by interceptor */
  }
}

async function loadModelRoutes() {
  routesLoading.value = true
  try {
    const res = await getModelRoutes()
    modelRoutes.value = res?.routes || []
  } catch {
    /* handled by interceptor */
  } finally {
    routesLoading.value = false
  }
}

function openEditRoute(record) {
  routeForm.route_id = record.route_id
  routeForm.capability = record.capability
  routeForm.profile = record.profile
  routeForm.model_id = record.model_id || ''
  routeForm.max_tokens = record.max_tokens ?? 4096
  routeForm.temperature = record.temperature ?? 0.7
  routeFormVisible.value = true
}

function openRouteDetail(record) {
  routeDetail.value = record
  routeDetailVisible.value = true
}

async function submitRouteEdit() {
  routeSubmitting.value = true
  try {
    await updateModelRoute(routeForm.route_id, {
      model_id: routeForm.model_id,
      max_tokens: routeForm.max_tokens,
      temperature: routeForm.temperature,
    })
    message.success('模型路由已更新')
    routeFormVisible.value = false
    await loadModelRoutes()
  } catch {
    /* handled by interceptor */
  } finally {
    routeSubmitting.value = false
  }
}

// 从 MDM 加载下拉选项，失败时保留本地硬编码兜底
async function loadMdmOptions() {
  const { dimensionOptions, statusOptions } = useMdmDict()
  const [roles, autonomy, health] = await Promise.all([
    dimensionOptions('agent_role'),
    dimensionOptions('autonomy_level'),
    statusOptions('tool_health'),
  ])
  let hasFallback = false
  if (roles.length) roleOptions.value = roles
  else hasFallback = true
  if (autonomy.length) autonomyOptions.value = autonomy
  else hasFallback = true
  if (health.length) healthOptions.value = health
  else hasFallback = true
  if (hasFallback) {
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
}

watch(activeTab, (val) => {
  if (val === 'routes' && modelRoutes.value.length === 0) {
    loadModelRoutes()
  }
})

onMounted(async () => {
  await loadCapabilityNames()
  await loadLlmOptions()
  await loadMdmOptions()
  await loadAgents()
})
</script>

<style scoped>
.agent-manager-page {
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 0 8px;
}

.page-header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.tabs-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.tabs-card :deep(.ant-card-body) {
  padding: 4px 20px 20px;
}

.tabs-card :deep(.ant-tabs-tab) {
  font-size: 13px;
  padding: 12px 4px;
}

.tab-count {
  display: inline-block;
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  padding: 0 5px;
  margin-left: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  background: var(--light-bg-active);
  border-radius: 9px;
  text-align: center;
}

.planned-tag {
  margin-left: 6px;
  font-size: 10px;
  line-height: 14px;
  padding: 0 5px;
  border-radius: var(--radius-sm);
}

.routes-alert {
  margin-bottom: 12px;
}

.routes-desc {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.routes-desc-para {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.routes-desc-para strong {
  color: var(--text-primary);
  font-weight: 600;
}

/* 表格样式 */
.agent-table :deep(.ant-table) {
  font-size: 13px;
}

.agent-table :deep(.ant-table-thead > tr > th) {
  background: var(--light-bg-hover);
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 12px;
}

.agent-table :deep(.ant-table-tbody > tr > td) {
  padding: 10px 16px;
}

.name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.name-text {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 13px;
}

.status-tag {
  margin: 0;
  font-size: 11px;
  line-height: 18px;
  padding: 0 6px;
  border-radius: var(--radius-sm);
}

.status-dev {
  background: var(--light-bg-active);
  color: var(--text-muted);
  border: 1px solid var(--border-light);
}

.text-secondary {
  color: var(--text-secondary);
  font-size: 13px;
}

.text-muted {
  color: var(--text-muted);
  font-size: 13px;
}

/* 详情抽屉 */
.detail-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  padding-left: 8px;
  border-left: 3px solid var(--primary);
}

.section-hint {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 8px;
}

.collapse-title {
  display: inline-flex;
  align-items: baseline;
  border-left: none;
  padding-left: 0;
}

.eligibility-collapse {
  background: transparent;
}

.eligibility-collapse :deep(.ant-collapse-header) {
  padding: 8px 0 !important;
  align-items: center;
}

.eligibility-collapse :deep(.ant-collapse-content-box) {
  padding: 8px 0 !important;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.binding-list {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}

.binding-tag {
  margin: 0;
  font-size: 10px;
  line-height: 16px;
  padding: 0 4px;
  background: var(--light-bg-active);
  border-color: var(--border-light);
  color: var(--text-secondary);
}

.agent-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}

.form-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin: -4px 0 12px;
  line-height: 1.5;
}

/* 模型单元格（优先 + 备选） */
.model-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.model-primary {
  color: var(--text-primary);
  font-size: 13px;
}

.model-secondary {
  color: var(--text-muted);
  font-size: 11px;
}

/* 测试对话抽屉 */
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 12px;
}

.chat-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  background: var(--light-bg-hover);
  border-radius: var(--radius-sm);
  font-size: 12px;
}

.chat-meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.chat-meta-label {
  display: inline-block;
  padding: 1px 6px;
  font-size: 10px;
  border-radius: 3px;
  background: var(--primary);
  color: #fff;
  font-weight: 500;
}

/* 测试对话抽屉 - messages 区域 */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  background: var(--light-bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  min-height: 320px;
  max-height: calc(100vh - 280px);
}

.chat-empty {
  color: var(--text-muted);
  text-align: center;
  padding: 60px 0;
  font-size: 13px;
}

.chat-msg {
  margin-bottom: 14px;
}

.chat-msg-user .chat-msg-content {
  background: var(--primary);
  color: #fff;
}

.chat-msg-assistant .chat-msg-content {
  background: var(--light-bg-hover);
  color: var(--text-primary);
}

.chat-msg-role {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.chat-msg-content {
  display: inline-block;
  padding: 8px 12px;
  border-radius: var(--radius);
  font-size: 13px;
  line-height: 1.6;
  max-width: 85%;
  word-break: break-word;
  white-space: pre-wrap;
}

.chat-typing {
  color: var(--text-muted);
  font-style: italic;
}

.chat-input-bar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.avatar-fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--light-bg-active);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}
</style>
