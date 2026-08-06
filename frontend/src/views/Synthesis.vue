<template>
  <div class="synthesis">
    <div class="page-header">
      <h1 class="page-title">工艺深化工作台</h1>
      <p class="page-subtitle">第二层工艺深化：针对初筛通过的候选配方，进行详细合成路径规划并产出可执行工艺方案</p>
    </div>

    <!-- 主视图切换：深化工作台（工艺人员主场景） / 临时逆合成规划（高级能力） -->
    <div class="mode-switch">
      <a-radio-group v-model:value="mode" class="mode-radio">
        <a-radio-button value="workbench"><ToolOutlined /> 深化工作台</a-radio-button>
        <a-radio-button value="planner"><BranchesOutlined /> 临时逆合成规划</a-radio-button>
      </a-radio-group>
      <a-button v-if="mode === 'workbench'" type="primary" ghost size="small" :loading="workbenchLoading" @click="loadWorkbench">
        <SyncOutlined /> 刷新流水线
      </a-button>
    </div>

    <!-- ═══════════════ 工作台视图：候选深化流水线 ═══════════════ -->
    <template v-if="mode === 'workbench'">
      <div class="pipeline-filter">
        <a-tabs v-model:activeKey="statusFilter" :animated="false" @change="onFilterChange">
          <a-tab-pane key="all" tab="全部" />
          <a-tab-pane key="feasible" tab="待深化" />
          <a-tab-pane key="process_planning" tab="深化中" />
          <a-tab-pane key="process_confirmed" tab="工艺已确认" />
          <a-tab-pane key="ready_for_experiment" tab="可下达实验" />
        </a-tabs>
      </div>

      <!-- 深化流水线候选列表 -->
      <a-card class="pipeline-card" :bordered="false">
        <a-table
          :data-source="pipelineItems"
          :columns="pipelineColumns"
          :loading="workbenchLoading"
          :pagination="false"
          row-key="candidate_id"
          size="small"
          :custom-row="pipelineRowProps"
          @row-click="selectCandidate"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <div class="cand-name">{{ record.name || record.candidate_id }}</div>
              <div class="cand-sub">{{ record.source || record.candidate_type || '' }}</div>
            </template>
            <template v-else-if="column.key === 'status'">
              <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
            </template>
            <template v-else-if="column.key === 'schemes'">
              <span :class="{ 'num': true, 'scheme-empty': !record.scheme_count }">
                {{ record.scheme_count || 0 }}
              </span>
            </template>
            <template v-else-if="column.key === 'owner'">
              <span v-if="record.owner" class="owner-name">{{ record.owner }}</span>
              <span v-else class="muted">—</span>
              <div v-if="record.assigned_role" class="role-hint">{{ roleLabel(record.assigned_role) }}</div>
            </template>
            <template v-else-if="column.key === 'action'">
              <a-button
                type="link"
                size="small"
                class="action-link"
                @click.stop="selectCandidate(record)"
              >
                深化 / 查看
              </a-button>
            </template>
          </template>
          <template #emptyText>
            <EmptyState type="data" description="当前没有进入工艺深化流水线的候选" />
          </template>
        </a-table>
      </a-card>

      <!-- 选中候选的工艺深化工作区 -->
      <div v-if="selected" class="workspace">
        <a-card class="workspace-card" :bordered="false">
          <template #title>
            <span class="card-title-text"><ToolOutlined /> 工艺深化工作区</span>
          </template>

          <!-- 候选信息 -->
          <div class="candidate-info">
            <div class="cand-head">
              <div class="cand-icon"><MoleculeView :smiles="selected.smiles" :size="96" /></div>
              <div class="cand-meta">
                <div class="cand-title">{{ selected.name || selected.candidate_id }}</div>
                <div class="cand-tags">
                  <a-tag color="orange">{{ typeLabel(selected.candidate_type) }}</a-tag>
                  <a-tag :color="statusColor(selected.status)">{{ statusLabel(selected.status) }}</a-tag>
                  <a-tag v-if="selected.owner" color="blue">责任人 {{ selected.owner }}</a-tag>
                </div>
                <div v-if="selected.smiles" class="cand-smiles">
                  <span class="muted">SMILES：</span><code>{{ selected.smiles }}</code>
                </div>
              </div>
            </div>

            <!-- 深化操作 -->
            <div class="deepen-actions">
              <a-button
                type="primary"
                :loading="deepeningLoading"
                @click="runDeepening"
              >
                <ThunderboltOutlined /> 执行工艺深化
              </a-button>
              <span class="action-hint">
                将调用对应高级能力（SCP 优先 / 本地回退）规划合成路径并做 DFT 可行性校验
              </span>
            </div>
          </div>

          <!-- 工艺方案（多路径比选 + 能力来源） -->
          <div v-if="schemes.length" class="scheme-list">
            <div v-for="scheme in schemes" :key="scheme.process_id" class="scheme-block">
              <div class="scheme-head">
                <div class="scheme-id">
                  <span class="scheme-label">工艺方案</span>
                  <code>{{ scheme.process_id }}</code>
                  <a-tag :color="schemeStatusColor(scheme.status)">{{ schemeStatusLabel(scheme.status) }}</a-tag>
                </div>
                <div class="scheme-meta">
                  <span v-if="scheme.owner" class="muted">负责人 {{ scheme.owner }}</span>
                  <span v-if="scheme.routes?.length" class="muted num">{{ scheme.routes.length }} 条路线</span>
                </div>
              </div>

              <!-- 路线比选 -->
              <div v-if="scheme.routes?.length" class="scheme-routes">
                <a-row :gutter="12">
                  <a-col v-for="route in scheme.routes" :key="route.route_id" :xs="24" :md="12" :lg="8">
                    <div class="scheme-route">
                      <div class="route-head">
                        <span class="route-name">路线 {{ route.route_id }}</span>
                        <a-tag :color="route.feasibility_score > 0.3 ? 'green' : 'orange'">
                          {{ route.is_feasible ? '可合成' : '需评估' }}
                        </a-tag>
                      </div>
                      <div class="route-stats">
                        <div class="stat"><span class="muted">步骤</span><span class="num">{{ route.step_count || 0 }}</span></div>
                        <div class="stat"><span class="muted">可行性</span><span class="num">{{ ((route.feasibility_score || 0) * 100).toFixed(0) }}%</span></div>
                        <div class="stat"><span class="muted">成本</span><span class="num">{{ route.estimated_cost || 0 }}</span></div>
                      </div>
                      <!-- DFT 校验结果 -->
                      <div v-if="route.dft" class="route-dft">
                        <a-tag :color="route.dft.overall_status === 'passed' ? 'green' : 'red'" size="small">
                          DFT {{ route.dft.overall_status === 'passed' ? '通过' : '不通过' }}
                        </a-tag>
                        <span v-if="route.dft.original_confidence != null" class="num muted">
                          置信度 {{ (route.dft.original_confidence * 100).toFixed(0) }}% → {{ (route.dft.adjusted_confidence * 100).toFixed(0) }}%
                        </span>
                      </div>
                      <div v-else class="route-dft muted">DFT 待校验</div>
                      <!-- 分步反应 -->
                      <a-collapse v-if="route.steps?.length" :bordered="false" class="route-steps">
                        <a-collapse-panel key="steps" :header="`分步反应（${route.steps.length} 步）`">
                          <div v-for="(step, idx) in route.steps" :key="idx" class="step-block">
                            <div class="step-title">步骤 {{ idx + 1 }}
                              <a-tag v-if="step.reaction_type" color="purple">{{ step.reaction_type }}</a-tag>
                            </div>
                            <div v-if="step.reaction_smiles" class="step-row">
                              <span class="step-key">反应:</span><code class="step-val">{{ step.reaction_smiles }}</code>
                            </div>
                            <div v-if="step.conditions" class="step-row">
                              <span class="step-key">条件:</span><span class="step-val">{{ step.conditions }}</span>
                            </div>
                          </div>
                        </a-collapse-panel>
                      </a-collapse>
                    </div>
                  </a-col>
                </a-row>
              </div>
              <div v-else class="scheme-empty-hint muted">该方案暂无候选路线，请执行工艺深化</div>

              <!-- 能力来源（AI 透明性） -->
              <div v-if="scheme.evidence_refs?.length" class="evidence-block">
                <div class="evidence-title"><SafetyCertificateOutlined /> 能力来源</div>
                <div class="evidence-list">
                  <div v-for="(ev, i) in scheme.evidence_refs" :key="i" class="evidence-item">
                    <a-tag :color="ev.status === 'success' ? 'green' : 'red'" size="small">
                      {{ ev.source === 'scp' ? 'SCP' : '本地' }}
                    </a-tag>
                    <span class="ev-cap">{{ ev.capability }}</span>
                    <span v-if="ev.tool" class="ev-tool muted">{{ ev.tool }}</span>
                    <span class="ev-detail muted">{{ ev.detail }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="scheme-empty-hint">
            <EmptyState :type="deepeningLoading ? 'loading' : 'data'" description="尚无工艺方案，点击『执行工艺深化』生成" />
          </div>
        </a-card>
      </div>
    </template>

    <!-- ═══════════════ 临时逆合成规划（高级能力） ═══════════════ -->
    <template v-else>
      <div class="planner-tip"><InfoCircleOutlined /> 该工具用于工艺人员对任一目标分子做临时逆合成规划与机理分析，不绑定候选流水线。</div>

      <!-- 两列布局：左侧输入表单 + 右侧 Agent 信息面板 -->
      <div class="synthesis-layout">
        <div class="synthesis-main">
          <a-card class="input-card" :bordered="false">
            <a-form layout="horizontal" :label-col="{ span: 4 }" :wrapper-col="{ span: 18 }">
              <a-form-item label="目标分子 SMILES" extra="输入目标分子的 SMILES 表示，例如 CCO（乙醇）或 c1ccccc1（苯）">
                <a-input
                  v-model:value="smiles"
                  placeholder="例如 CCO"
                  allow-clear
                  class="smiles-input"
                  @press-enter="promptPlan"
                />
                <div class="template-chips">
                  <span class="chip-label">模板：</span>
                  <a-tag
                    v-for="t in templates"
                    :key="t.smiles"
                    class="template-chip"
                    role="button"
                    tabindex="0"
                    @click="smiles = t.smiles"
                    @keydown.enter.prevent="smiles = t.smiles"
                  >{{ t.label }} · {{ t.smiles }}</a-tag>
                </div>
                <div v-if="smiles && smiles.trim()" class="smiles-preview">
                  <span class="preview-label">分子结构预览：</span>
                  <MoleculeView :smiles="smiles" :size="160" />
                </div>
              </a-form-item>
            </a-form>
            <a-alert
              v-if="isFormulaNotSmiles"
              message="从 Discovery 接收的晶体 formula 不是 SMILES 格式，可能需要转换"
              type="warning"
              show-icon
              style="margin-top: 12px"
            />
            <a-alert v-if="serviceError" type="error" show-icon style="margin-top: 12px; white-space: pre-line">
              <template #message>逆合成服务暂不可用</template>
              <template #description>
                <div>{{ serviceError }}</div>
                <div class="service-error-actions">
                  <a-button size="small" type="primary" ghost @click="onPlan">重新尝试</a-button>
                  <a-button size="small" @click="openManualEntry">手动填写合成路径</a-button>
                </div>
              </template>
            </a-alert>

            <div v-if="loading" class="plan-progress">
              <div v-for="(step, idx) in planSteps" :key="idx" class="plan-step" :class="`is-${step.status}`">
                <span class="plan-step-icon">
                  <CheckCircleFilled v-if="step.status === 'finish'" />
                  <LoadingOutlined v-else-if="step.status === 'process'" />
                  <CloseCircleFilled v-else-if="step.status === 'error'" />
                  <ClockCircleOutlined v-else />
                </span>
                <span class="plan-step-label">{{ step.label }}</span>
                <span v-if="step.status === 'process' && idx === 2" class="plan-step-elapsed">已等待 {{ elapsedSeconds }}s</span>
              </div>
            </div>
          </a-card>
        </div>

        <aside class="synth-agent-panel">
          <a-spin :spinning="agentLoading">
            <div v-if="selectedAgent" class="synth-agent-card">
              <div class="synth-panel-title">执行智能体</div>
              <div v-if="capableAgents.length > 1" class="agent-select-block">
                <a-select v-model:value="selectedAgentId" size="small" style="width: 100%" @change="onAgentChange">
                  <a-select-option v-for="a in capableAgents" :key="a.id" :value="a.id">{{ a.name }}</a-select-option>
                </a-select>
              </div>
              <div class="synth-head">
                <div class="synth-avatar">{{ selectedAgent.avatar || '🤖' }}</div>
                <div class="synth-info">
                  <div class="synth-name">{{ selectedAgent.name || '合成规划' }}</div>
                  <div class="synth-tags-row">
                    <a-tag color="orange" class="synth-role-tag">合成规划</a-tag>
                    <a-tag v-if="selectedAgent.is_builtin" color="default" class="synth-builtin-tag">内置</a-tag>
                  </div>
                </div>
              </div>
              <div class="synth-section">
                <div class="synth-section-title">职责描述</div>
                <div class="synth-desc">{{ selectedAgent.description || '基于 ASKCOS 逆合成规划的多路径并行探索与机理分析' }}</div>
              </div>
              <div v-if="selectedAgent.expertise?.length" class="synth-section">
                <div class="synth-section-title">专长</div>
                <div class="synth-tags">
                  <a-tag v-for="e in selectedAgent.expertise" :key="e" size="small" class="synth-tag">{{ e }}</a-tag>
                </div>
              </div>
              <div class="synth-action-block">
                <a-button type="primary" block :loading="loading" :disabled="!canRunPlan" @click="promptPlan">
                  <BranchesOutlined /> 规划合成路径
                </a-button>
                <div v-if="loading" class="synth-action-hint">智能体正在连接逆合成服务并搜索候选路线，通常需要 30-60 秒</div>
                <div v-else-if="!canRunPlan" class="synth-action-hint">请先输入目标分子 SMILES</div>
              </div>
            </div>
            <EmptyState v-else-if="!agentLoading" type="data" description="暂无合成规划 Agent" />
          </a-spin>
        </aside>
      </div>

      <!-- Result -->
      <div v-if="routes.length" class="result-section">
        <a-card class="comparison-card" :bordered="false">
          <template #title><span class="card-title-text"><BarChartOutlined /> 综合成本-可行性-步骤数 三维对比</span></template>
          <div ref="scatterRef" class="scatter-chart"></div>
        </a-card>

        <a-row :gutter="16" class="routes-row">
          <a-col v-for="route in routes" :key="route.route_id" :xs="24" :md="12" :lg="8">
            <a-card class="route-card" :bordered="false">
              <template #title>
                <div class="route-header">
                  <span class="route-name">路线 {{ route.route_id }}</span>
                  <a-tag :color="route.feasibility_score > 0.3 ? 'green' : 'orange'">{{ route.is_feasible ? '可合成' : '需评估' }}</a-tag>
                </div>
              </template>
              <template #extra><span class="route-score num">{{ ((route.feasibility_score || 0) * 100).toFixed(0) }}分</span></template>
              <div class="route-meta">
                <div class="meta-row"><span class="meta-label">步骤数</span><span class="meta-value num">{{ route.step_count || 0 }}</span></div>
                <div class="meta-row">
                  <span class="meta-label">置信度</span>
                  <a-progress :percent="Math.round((dftAdjustedConfidence(route) || route.confidence || 0) * 100)" size="small" :status="dftStatus(route.route_id) === 'done' && dftResults[route.route_id]?.overall_status === 'failed' ? 'exception' : 'active'" />
                </div>
                <div class="meta-row"><span class="meta-label">综合成本</span><span class="meta-value num">{{ route.estimated_cost || 0 }}</span></div>
              </div>
              <a-collapse :bordered="false" class="steps-collapse">
                <a-collapse-panel key="steps" :header="`分步反应式（${route.steps?.length || 0} 步）`">
                  <div v-for="(step, idx) in route.steps" :key="idx" class="step-block">
                    <div class="step-title">
                      步骤 {{ idx + 1 }}
                      <a-tag color="blue" class="num">{{ ((step.score || 0) * 100).toFixed(0) }}%</a-tag>
                      <a-tag v-if="step.reaction_type" color="purple">{{ step.reaction_type }}</a-tag>
                    </div>
                    <div v-if="step.reaction_smiles" class="step-row"><span class="step-key">反应:</span><code class="step-val">{{ step.reaction_smiles }}</code></div>
                    <div v-if="step.conditions" class="step-row"><span class="step-key">条件:</span><span class="step-val">{{ step.conditions }}</span></div>
                    <div v-if="step.reactants?.length" class="step-row">
                      <span class="step-key">反应物:</span>
                      <div class="reactant-preview">
                        <div v-for="r in step.reactants" :key="r" class="reactant-item">
                          <MoleculeView :smiles="r" :size="80" />
                          <code class="reactant-smiles">{{ r.length > 18 ? r.slice(0, 15) + '…' : r }}</code>
                        </div>
                      </div>
                    </div>
                  </div>
                </a-collapse-panel>
              </a-collapse>
              <div class="dft-section">
                <div class="dft-header">
                  <span class="dft-title"><ThunderboltOutlined /> DFT 可行性校验</span>
                  <a-button size="small" type="primary" ghost :loading="dftLoading[route.route_id]" @click="verifyDFT(route)">
                    {{ dftStatus(route.route_id) === 'done' ? '重新校验' : '启动校验' }}
                  </a-button>
                </div>
                <div v-if="dftResults[route.route_id]" class="dft-results">
                  <div v-for="sr in dftResults[route.route_id].step_results" :key="sr.step_idx" class="dft-step-row">
                    <div class="dft-step-head">
                      <span class="dft-step-name">步骤 {{ sr.step_idx + 1 }}</span>
                      <a-tag :color="sr.status === 'passed' ? 'green' : 'red'">{{ sr.status === 'passed' ? '通过' : '不通过' }}</a-tag>
                      <span class="dft-energy num" :class="{ 'energy-fail': sr.status === 'failed' }">ΔE = {{ sr.energy_change > 0 ? '+' : '' }}{{ sr.energy_change }} {{ sr.unit }}</span>
                    </div>
                    <a-progress :percent="100" :status="sr.status === 'passed' ? 'success' : 'exception'" size="small" :show-info="false" />
                  </div>
                  <a-alert
                    :type="dftResults[route.route_id].overall_status === 'passed' ? 'success' : 'warning'"
                    :message="`整体校验：${dftResults[route.route_id].overall_status === 'passed' ? '通过' : '不通过'}`"
                    :description="`置信度 ${((dftResults[route.route_id].original_confidence) * 100).toFixed(0)}% → ${((dftResults[route.route_id].adjusted_confidence) * 100).toFixed(0)}%`"
                    show-icon
                    style="margin-top: 8px"
                  />
                </div>
                <div v-else-if="dftLoading[route.route_id]" class="dft-pending"><a-spin size="small" /><span>校验中…</span></div>
                <div v-else class="dft-pending">待校验</div>
              </div>
            </a-card>
          </a-col>
        </a-row>

        <a-card class="network-card" :bordered="false">
          <template #title><span class="card-title-text"><NodeIndexOutlined /> 反应机理网络</span></template>
          <div v-if="networkLoading" class="app-loading-area"><a-spin size="small" /> 正在解析反应网络…</div>
          <div v-else>
            <ReactionNetwork :nodes="network.nodes" :edges="network.edges" :target="network.target" />
            <a-alert v-if="networkError" type="warning" show-icon style="margin-top: 12px">
              <template #message>反应网络解析提示</template>
              <template #description>{{ networkError }}</template>
            </a-alert>
            <div v-else-if="!network.nodes?.length" class="network-empty-hint">暂无反应网络数据</div>
          </div>
        </a-card>

        <a-card class="action-card" :bordered="false">
          <a-button type="primary" @click="promptSendToExperiment"><ExperimentOutlined /> 发送到实验</a-button>
        </a-card>
      </div>
      <div v-else class="empty-state">
        <BranchesOutlined class="empty-state-icon" />
        输入 SMILES 开始规划合成路径
      </div>
    </template>

    <a-modal v-model:open="confirmVisible" :title="confirmTitle" @ok="onConfirmOk" @cancel="confirmVisible = false">
      <p>{{ confirmContent }}</p>
    </a-modal>

    <!-- 手动填写合成路径（逆合成服务不可用时的业务兜底） -->
    <a-drawer
      :open="manualVisible"
      title="手动填写合成路径"
      placement="right"
      width="640px"
      @update:open="(v) => (manualVisible = v)"
    >
      <p class="manual-tip">逆合成服务暂不可用。您可以基于经验手动登记该目标分子的合成路径，保存后将被记录并计入统计。</p>
      <div class="manual-target"><span class="manual-label">目标分子</span><code>{{ smiles }}</code></div>
      <div v-for="(step, idx) in manualSteps" :key="idx" class="manual-step">
        <div class="manual-step-header">
          <span>步骤 {{ idx + 1 }}</span>
          <a-button v-if="manualSteps.length > 1" type="link" size="small" danger @click="manualSteps.splice(idx, 1)">删除</a-button>
        </div>
        <a-input v-model:value="step.reactants" placeholder="反应物 SMILES，多个用英文句点分隔，如 CC=O.[H][H]" class="manual-step-input" />
        <a-input v-model:value="step.conditions" placeholder="反应条件（可选），如 NaBH4, MeOH, 0°C" class="manual-step-input" />
      </div>
      <a-button type="dashed" block @click="manualSteps.push({ reactants: '', conditions: '' })">+ 添加步骤</a-button>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="manualSaving" @click="manualVisible = false">取消</a-button>
          <a-button type="primary" :loading="manualSaving" @click="saveManualRoute">保存路线</a-button>
        </a-space>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import {
  BranchesOutlined,
  ExperimentOutlined,
  ThunderboltOutlined,
  NodeIndexOutlined,
  BarChartOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  ClockCircleOutlined,
  LoadingOutlined,
  ToolOutlined,
  SyncOutlined,
  InfoCircleOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons-vue'
import { getReactionNetwork, verifyRouteWithDFT } from '@/api/experiments'
import { planSynthesisAsync, getSynthesisTask, createManualRoute } from '@/api/synthesis'
import { getProcessEngineerWorkbench, runProcessDeepening } from '@/api/candidates'
import { listAgents } from '@/api/agents'
import { useMdmDict } from '@/utils/mdmDict'
import { getUserId } from '@/api/client'
import MoleculeView from '@/components/MoleculeView.vue'
import ReactionNetwork from '@/components/ReactionNetwork.vue'
import ResearchContextBanner from '@/components/ResearchContextBanner.vue'
import EmptyState from '@/components/EmptyState.vue'

const currentRoute = useRoute()
const router = useRouter()
const LAST_SMILES_KEY = 'battery_synthesis:last_smiles'
const currentScenarioId = ref('')
const smiles = ref(currentRoute.query.smiles || currentRoute.query.formula || 'CCO')
const serviceError = ref('')
const isFormulaNotSmiles = computed(() => !!currentRoute.query.formula && !currentRoute.query.smiles)
const routes = ref([])
const network = ref({ nodes: [], edges: [], target: '' })
const networkLoading = ref(false)
const networkError = ref('')
const loading = ref(false)

// ── 主视图模式：workbench（深化工作台）/ planner（临时逆合成规划） ──
const mode = ref('workbench')

// ═══════════════════════════════════════════════════════════════
// 工艺人员工作台（Phase B）
// ═══════════════════════════════════════════════════════════════
const workbenchLoading = ref(false)
const pipelineItems = ref([])
const pipelineStatuses = ref([])
const statusFilter = ref('all')
const selectedItem = ref(null)
const selected = ref(null)
const schemes = ref([])
const deepeningLoading = ref(false)
const currentOwner = getUserId() || ''

const STATUS_META = {
  feasible: { label: '待深化', color: 'orange' },
  process_planning: { label: '深化中', color: 'blue' },
  process_confirmed: { label: '工艺已确认', color: 'purple' },
  ready_for_experiment: { label: '可下达实验', color: 'green' },
  screening: { label: '初筛中', color: 'default' },
  rejected: { label: '淘汰', color: 'red' },
}
const statusLabel = (s) => STATUS_META[s]?.label || s || '—'
const statusColor = (s) => STATUS_META[s]?.color || 'default'
const roleLabel = (r) => (r === 'formulator' ? '配方设计' : r === 'process_engineer' ? '工艺人员' : r || '')
const typeLabel = (t) => (t === 'crystal' ? '晶体' : t === 'polymer' ? '聚合物' : t || '候选')
const SCHEME_STATUS_META = {
  draft: { label: '草稿', color: 'default' },
  reviewing: { label: '评审中', color: 'blue' },
  confirmed: { label: '已确认', color: 'green' },
  abandoned: { label: '已放弃', color: 'red' },
}
const schemeStatusLabel = (s) => SCHEME_STATUS_META[s]?.label || s || '—'
const schemeStatusColor = (s) => SCHEME_STATUS_META[s]?.color || 'default'

const pipelineColumns = [
  { title: '候选', key: 'name' },
  { title: '状态', key: 'status', width: 110 },
  { title: '工艺方案', key: 'schemes', width: 90, align: 'center' },
  { title: '责任人', key: 'owner', width: 120 },
  { title: '操作', key: 'action', width: 100, align: 'right' },
]

function pipelineRowProps(record) {
  return { style: { cursor: 'pointer' } }
}

async function loadWorkbench() {
  workbenchLoading.value = true
  try {
    const res = await getProcessEngineerWorkbench(
      statusFilter.value && statusFilter.value !== 'all' ? statusFilter.value : '',
    )
    pipelineItems.value = Array.isArray(res?.items) ? res.items : []
    pipelineStatuses.value = res?.pipeline_statuses || []
    // 若已选中某候选，刷新其工艺方案
    if (selected.value) {
      const updated = pipelineItems.value.find((it) => it.candidate.candidate_id === selected.value.candidate_id)
      if (updated) {
        selected.value = updated.candidate
        schemes.value = updated.process_schemes || []
        selectedItem.value = updated
      }
    }
  } catch {
    pipelineItems.value = []
  } finally {
    workbenchLoading.value = false
  }
}

function onFilterChange() {
  loadWorkbench()
}

function selectCandidate(record) {
  selected.value = record.candidate
  selectedItem.value = record
  schemes.value = record.process_schemes || []
}

async function runDeepening() {
  if (!selected.value) return
  deepeningLoading.value = true
  try {
    const scheme = await runProcessDeepening(selected.value.candidate_id, {
      candidate_id: selected.value.candidate_id,
      owner: currentOwner,
      notes: `工艺深化：${selected.value.name || selected.value.candidate_id}`,
    })
    message.success(`工艺深化完成，生成 ${scheme?.routes?.length || 0} 条候选工艺路线`)
    await loadWorkbench()
  } catch (err) {
    message.error((err?.response?.data?.detail) || '工艺深化失败，请稍后重试', 6)
  } finally {
    deepeningLoading.value = false
  }
}

// ═══════════════════════════════════════════════════════════════
// 合成规划 Agent 信息（临时规划面板展示）
// ═══════════════════════════════════════════════════════════════
const capableAgents = ref([])
const selectedAgentId = ref('')
const agentLoading = ref(false)

const selectedAgent = computed(() =>
  capableAgents.value.find((a) => a.id === selectedAgentId.value) || capableAgents.value[0] || null
)

async function loadCapableAgents() {
  agentLoading.value = true
  try {
    const res = await listAgents()
    const list = Array.isArray(res) ? res : (res?.agents || [])
    const byRole = list.filter((a) => a.role === 'synthesis_planning')
    const matched = byRole.length ? byRole : list.filter((a) => a.id && a.id.includes('synthesis'))
    capableAgents.value = matched.length ? matched : []
    if (capableAgents.value.length) selectedAgentId.value = capableAgents.value[0].id
  } catch {
    capableAgents.value = []
  } finally {
    agentLoading.value = false
  }
}

function onAgentChange(id) {
  selectedAgentId.value = id
}

const canRunPlan = computed(() => !!smiles.value.trim())

// DFT 校验状态：route_id -> { result, loading }
const dftResults = ref({})
const dftLoading = ref({})

const scatterRef = ref(null)
let scatterChart = null

const templates = [
  { label: '乙醇', smiles: 'CCO' },
  { label: '异丙醇', smiles: 'CC(C)O' },
  { label: '环己烷', smiles: 'C1CCCCC1' },
  { label: '环氧乙烷', smiles: 'C1CO1' },
]

function isValidSmiles(s) {
  const v = (s || '').trim()
  if (!v) return { ok: false, reason: 'SMILES 不能为空' }
  if (!/^[A-Za-z0-9\[\]\(\)=#$:.+\-\\/@@]*$/.test(v)) return { ok: false, reason: 'SMILES 含有非法字符' }
  const stack = []
  const pairs = { '(': ')', '[': ']' }
  for (const ch of v) {
    if (ch === '(' || ch === '[') stack.push(pairs[ch])
    else if (ch === ')' || ch === ']') {
      if (stack.pop() !== ch) return { ok: false, reason: 'SMILES 括号不匹配' }
    }
  }
  if (stack.length) return { ok: false, reason: 'SMILES 括号未闭合' }
  if (!/^([A-Za-z][a-z]?|c|n|o|s|p|\d|\(|\)|\[|\]|\#|\=|\\|\/|\@|\+|\-|\.|\:|\$)/.test(v)) return { ok: false, reason: 'SMILES 起始字符不合法' }
  return { ok: true }
}

const { statusOptions: mdmStatusOptions, dimensionOptions: mdmDimensionOptions } = useMdmDict()
async function loadMdmOptions() {
  try {
    await Promise.all([mdmStatusOptions('synthesis_task'), mdmDimensionOptions('priority')])
  } catch (e) {
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
}

onMounted(() => {
  if (!currentRoute.query.smiles && !currentRoute.query.formula) {
    const saved = sessionStorage.getItem(LAST_SMILES_KEY)
    if (saved) smiles.value = saved
  }
  if (currentRoute.query.scenario_id) currentScenarioId.value = String(currentRoute.query.scenario_id)
  window.addEventListener('resize', resizeScatter)
  loadMdmOptions()
  loadCapableAgents()
  // 工作台主导：进入页面默认加载深化流水线
  loadWorkbench()
})

watch(
  () => smiles.value,
  (val) => {
    if (val) sessionStorage.setItem(LAST_SMILES_KEY, val)
  },
)

function dftStatus(routeId) {
  if (dftLoading.value[routeId]) return 'loading'
  if (dftResults.value[routeId]) return 'done'
  return 'idle'
}

function dftAdjustedConfidence(route) {
  const r = dftResults.value[route.route_id]
  return r ? r.adjusted_confidence : null
}

const confirmVisible = ref(false)
const confirmTitle = ref('')
const confirmContent = ref('')
let confirmCallback = null

function showConfirm(title, content, callback) {
  confirmTitle.value = title
  confirmContent.value = content
  confirmCallback = callback
  confirmVisible.value = true
}

function onConfirmOk() {
  confirmVisible.value = false
  confirmCallback?.()
}

function promptPlan() {
  const check = isValidSmiles(smiles.value)
  if (!check.ok) {
    message.warning(`SMILES 输入不合法：${check.reason}。请检查或从模板选择。`)
    return
  }
  onPlan()
}

function promptSendToExperiment() {
  const best = routes.value[0]
  showConfirm(
    '发送到实验',
    `目标：${best?.target_smiles || smiles.value}。确认将该合成目标发送到实验页面吗？`,
    sendToExperiment,
  )
}

function sendToExperiment() {
  const query = { smiles: smiles.value }
  if (currentScenarioId.value) query.scenario_id = currentScenarioId.value
  router.push({ path: '/experiments', query })
  message.info('已发送合成目标到实验页面')
}

// ---- 异步规划：提交 → 轮询 → 分步进度反馈 ----
const PLAN_STEPS_TEMPLATE = [
  '任务已提交',
  '连接逆合成服务',
  '并行搜索候选路线',
  '解析结果与可行性评分',
]
const planSteps = ref([])
const elapsedSeconds = ref(0)
let pollTimer = null
let elapsedTimer = null

function resetPlanProgress() {
  planSteps.value = PLAN_STEPS_TEMPLATE.map((label, idx) => ({ label, status: idx === 0 ? 'process' : 'wait' }))
  elapsedSeconds.value = 0
}

function advancePlanStep(stepIdx, status = 'process') {
  planSteps.value = planSteps.value.map((s, idx) => {
    if (idx < stepIdx) return { ...s, status: 'finish' }
    if (idx === stepIdx) return { ...s, status }
    return { ...s, status: 'wait' }
  })
}

function failPlanStep(stepIdx) {
  planSteps.value = planSteps.value.map((s, idx) => {
    if (idx < stepIdx) return { ...s, status: 'finish' }
    if (idx === stepIdx) return { ...s, status: 'error' }
    return { ...s, status: 'wait' }
  })
}

function clearPlanTimers() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
  if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null }
}

async function pollTask(taskId, attempts = 0) {
  const MAX_ATTEMPTS = 90
  let task
  try {
    task = await getSynthesisTask(taskId)
  } catch {
    loading.value = false
    clearPlanTimers()
    return
  }
  if (task.status === 'success') {
    clearPlanTimers()
    planSteps.value = planSteps.value.map((s) => ({ ...s, status: 'finish' }))
    const result = task.result || {}
    routes.value = result.routes || []
    loading.value = false
    if (routes.value.length > 0) {
      loadNetwork(smiles.value.trim())
      message.success(`合成路径规划完成，共 ${result.count || routes.value.length} 条候选路线`)
      nextTick(renderScatter)
    } else {
      message.warning('未找到可行合成路径')
    }
    return
  }
  if (task.status === 'failed') {
    clearPlanTimers()
    failPlanStep(1)
    loading.value = false
    serviceError.value = `${task.error || '规划失败'}\n您可以重新尝试，或改用手动填写路线。`
    routes.value = []
    return
  }
  if (task.status === 'running') advancePlanStep(2)
  else advancePlanStep(1)
  if (attempts >= MAX_ATTEMPTS) {
    clearPlanTimers()
    failPlanStep(2)
    loading.value = false
    serviceError.value = '规划任务长时间未完成，服务可能负载过高。\n您可以重新尝试，或改用手动填写路线。'
    return
  }
  pollTimer = setTimeout(() => pollTask(taskId, attempts + 1), 1500)
}

async function onPlan() {
  if (!smiles.value.trim()) return
  clearPlanTimers()
  loading.value = true
  serviceError.value = ''
  networkError.value = ''
  routes.value = []
  network.value = { nodes: [], edges: [], target: '' }
  dftResults.value = {}
  dftLoading.value = {}
  resetPlanProgress()
  elapsedTimer = setInterval(() => { elapsedSeconds.value += 1 }, 1000)
  try {
    const res = await planSynthesisAsync({
      smiles: smiles.value.trim(),
      num_routes: 3,
      scenario_id: currentScenarioId.value,
    })
    advancePlanStep(1)
    await pollTask(res.task_id)
  } catch {
    clearPlanTimers()
    loading.value = false
    planSteps.value = []
  }
}

// ---- 手动填写合成路径（服务不可用时的业务兜底） ----
const manualVisible = ref(false)
const manualSaving = ref(false)
const manualSteps = ref([{ reactants: '', conditions: '' }])

function openManualEntry() {
  manualSteps.value = [{ reactants: '', conditions: '' }]
  manualVisible.value = true
}

async function saveManualRoute() {
  const steps = manualSteps.value
    .map((s) => ({
      reactants: s.reactants.split('.').map((x) => x.trim()).filter(Boolean),
      conditions: s.conditions.trim(),
    }))
    .filter((s) => s.reactants.length > 0)
  if (steps.length === 0) { message.warning('请至少填写一步反应物'); return }
  manualSaving.value = true
  try {
    const res = await createManualRoute({ smiles: smiles.value.trim(), steps, scenario_id: currentScenarioId.value })
    const result = res.result || {}
    routes.value = result.routes || []
    serviceError.value = ''
    manualVisible.value = false
    message.success('手动路线已保存并记录')
    nextTick(renderScatter)
  } catch {
  } finally {
    manualSaving.value = false
  }
}

async function loadNetwork(targetSmiles) {
  networkLoading.value = true
  networkError.value = ''
  try {
    const res = await getReactionNetwork(targetSmiles)
    network.value = {
      nodes: Array.isArray(res?.nodes) ? res.nodes : [],
      edges: Array.isArray(res?.edges) ? res.edges : [],
      target: res?.target || targetSmiles,
    }
    if (!network.value.nodes.length) networkError.value = '未能解析出反应网络节点，可能是 ASKCOS 未返回有效合成树。'
  } catch (err) {
    network.value = { nodes: [], edges: [], target: targetSmiles }
    networkError.value = '反应网络加载失败：' + (err?.message || '未知错误')
  } finally {
    networkLoading.value = false
  }
}

async function verifyDFT(route) {
  dftLoading.value = { ...dftLoading.value, [route.route_id]: true }
  const { [route.route_id]: _removed, ...rest } = dftResults.value
  dftResults.value = rest
  try {
    const res = await verifyRouteWithDFT({ route })
    dftResults.value = { ...dftResults.value, [route.route_id]: res }
    if (res.overall_status === 'passed') message.success(`路线 ${route.route_id} DFT 校验通过`)
    else message.warning(`路线 ${route.route_id} DFT 校验未通过，置信度已下调`)
  } catch (err) {
    message.error('DFT 校验失败，请稍后重试或联系管理员', 6)
  } finally {
    dftLoading.value = { ...dftLoading.value, [route.route_id]: false }
  }
}

// E1.4: 散点图渲染
function buildScatterOption() {
  const data = routes.value.map((r) => ({
    name: r.route_id,
    value: [r.step_count || 0, (r.feasibility_score || 0) * 100, r.estimated_cost || 0],
  }))
  return {
    backgroundColor: 'transparent',
    tooltip: {
      formatter: (p) => {
        const [steps, feas, cost] = p.value
        return `<b>${p.data.name}</b><br/>步骤数：${steps}<br/>可行性：${feas.toFixed(0)}%<br/>综合成本：${cost}`
      },
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#dde0e6',
      textStyle: { color: '#1a1a2e', fontSize: 12 },
    },
    grid: { left: 50, right: 30, top: 30, bottom: 50 },
    xAxis: {
      name: '步骤数', nameLocation: 'middle', nameGap: 30,
      nameTextStyle: { color: '#6b7280', fontSize: 12 },
      splitLine: { lineStyle: { color: '#eef0f4' } },
    },
    yAxis: {
      name: '可行性评分', nameLocation: 'middle', nameGap: 40,
      nameTextStyle: { color: '#6b7280', fontSize: 12 },
      min: 0, max: 100,
      splitLine: { lineStyle: { color: '#eef0f4' } },
    },
    series: [
      {
        type: 'scatter',
        data,
        symbolSize: (val) => Math.max(12, val[2] * 6),
        itemStyle: { color: '#2050d0', opacity: 0.75, borderColor: '#2050d0', borderWidth: 2 },
        emphasis: { itemStyle: { shadowBlur: 12, shadowColor: '#2050d0', opacity: 1 } },
        label: { show: true, position: 'top', formatter: (p) => p.data.name, fontSize: 11, fontWeight: 600, color: '#1a1a2e' },
      },
    ],
  }
}

function renderScatter() {
  if (!scatterRef.value || !routes.value.length) return
  if (!scatterChart) scatterChart = echarts.init(scatterRef.value)
  scatterChart.setOption(buildScatterOption(), true)
  scatterChart.resize()
}

function resizeScatter() {
  scatterChart?.resize()
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeScatter)
  scatterChart?.dispose()
  scatterChart = null
  clearPlanTimers()
})

watch(
  () => routes.value,
  () => nextTick(renderScatter),
  { deep: true },
)
</script>

<style scoped>
.synthesis {
  width: 100%;
  max-width: 100%;
}

.input-card,
.comparison-card,
.network-card,
.action-card,
.route-card,
.pipeline-card,
.workspace-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  margin-bottom: 16px;
}

/* ── 主视图切换 ── */
.mode-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.mode-radio {
  flex: 1;
}
.planner-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--light-bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 8px 12px;
  margin-bottom: 16px;
}

.result-section {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.card-title-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.scatter-chart { width: 100%; height: 350px; }
.routes-row { margin-bottom: 8px; }

.route-header { display: flex; align-items: center; gap: 8px; }
.route-name { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.route-score { font-size: 18px; font-weight: 700; color: var(--primary); }
.route-meta { margin-bottom: 8px; }
.meta-row { display: flex; align-items: center; gap: 12px; padding: 4px 0; }
.meta-label { font-size: 12px; color: var(--text-secondary); width: 64px; flex-shrink: 0; }
.meta-value { font-size: 13px; color: var(--text-primary); font-weight: 600; flex: 1; }

.steps-collapse { margin: 4px 0; background: transparent; }
.steps-collapse :deep(.ant-collapse-header) { padding: 8px 0 !important; font-size: 13px; font-weight: 600; color: var(--text-primary); }
.steps-collapse :deep(.ant-collapse-content-box) { padding: 0 0 8px 0 !important; }
.step-block { padding: 8px 0; border-bottom: 1px solid var(--border-light); }
.step-block:last-child { border-bottom: none; }
.step-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.step-row { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 6px; font-size: 12px; }
.step-key { color: var(--text-secondary); width: 48px; flex-shrink: 0; padding-top: 2px; }
.step-val { color: var(--text-primary); font-family: 'JetBrains Mono', monospace; word-break: break-all; }
.reactant-preview { display: flex; flex-wrap: wrap; gap: 8px; }
.reactant-item { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.reactant-smiles { font-size: 10px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }

.dft-section { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border-light); }
.dft-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.dft-title { font-size: 13px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 4px; }
.dft-results { display: flex; flex-direction: column; gap: 8px; }
.dft-step-row { display: flex; flex-direction: column; gap: 4px; }
.dft-step-head { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.dft-step-name { color: var(--text-primary); font-weight: 500; }
.dft-energy { color: var(--text-secondary); margin-left: auto; }
.dft-energy.energy-fail { color: var(--error); font-weight: 600; }
.dft-pending { font-size: 12px; color: var(--text-muted); display: flex; align-items: center; gap: 8px; }
.network-empty-hint { color: var(--text-muted); font-size: 13px; text-align: center; padding: 16px 0; }

/* ===== 异步规划分步进度 ===== */
.plan-progress { margin-top: 16px; padding: 14px 16px; background: var(--light-bg); border: 1px solid var(--border-light); border-radius: var(--radius-lg, 8px); display: flex; flex-direction: column; gap: 10px; }
.plan-step { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-muted); }
.plan-step.is-process { color: var(--primary); font-weight: 500; }
.plan-step.is-finish { color: var(--success-color, #52c41a); }
.plan-step.is-error { color: var(--error-color, #ff4d4f); }
.plan-step-icon { display: inline-flex; width: 16px; justify-content: center; }
.plan-step-elapsed { margin-left: auto; font-size: 12px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.service-error-actions { margin-top: 10px; display: flex; gap: 8px; }

/* ===== 手动路线登记 ===== */
.manual-tip { font-size: 13px; color: var(--text-secondary); margin-bottom: 12px; }
.manual-target { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.manual-label { font-size: 13px; color: var(--text-secondary); }
.manual-step { border: 1px solid var(--border-light); border-radius: 8px; padding: 10px; margin-bottom: 10px; }
.manual-step-header { display: flex; justify-content: space-between; align-items: center; font-size: 13px; font-weight: 500; margin-bottom: 8px; }
.manual-step-input { margin-bottom: 8px; }

.num { font-variant-numeric: tabular-nums; }
.muted { color: var(--text-muted); }

.template-chips { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.chip-label { font-size: 12px; color: var(--text-muted); }
.template-chip { cursor: pointer; margin: 0; transition: border-color var(--transition), color var(--transition), background var(--transition); }
.template-chip:hover { border-color: var(--primary-border); color: var(--primary); background: var(--primary-bg); }
.template-chip:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.smiles-preview { display: flex; align-items: center; gap: 12px; margin-top: 10px; padding: 8px 12px; background: var(--light-bg); border-radius: var(--radius-md); border: 1px solid var(--border-light); }
.preview-label { font-size: 12px; color: var(--text-muted); flex-shrink: 0; }
.smiles-input { width: 100%; }

/* ── 两列布局：左侧表单 + 右侧 Agent 面板 ── */
.synthesis-layout { display: flex; gap: var(--space-md, 16px); align-items: flex-start; }
.synthesis-main { flex: 1; min-width: 0; }
.synth-agent-panel { flex-shrink: 0; width: 300px; }
.synth-agent-card { background: var(--realsee-surface, #fff); border: 1px solid var(--border, #e8e8e8); border-radius: var(--radius-xl, 12px); box-shadow: var(--shadow-card, 0 1px 3px rgba(0,0,0,0.05)); padding: var(--space-lg, 16px); display: flex; flex-direction: column; gap: var(--space-md, 12px); }
.synth-panel-title { font-size: var(--font-size-sm, 12px); font-weight: var(--font-weight-bold, 700); color: var(--text-muted, #8c8c8c); letter-spacing: 0.5px; text-transform: uppercase; padding-bottom: var(--space-sm, 8px); border-bottom: 1px solid var(--border-light, #f0f0f0); }
.agent-select-block { margin-bottom: 4px; }
.synth-head { display: flex; gap: var(--space-md, 12px); align-items: center; }
.synth-avatar { width: 48px; height: 48px; border-radius: var(--radius-md, 8px); background: var(--primary-bg, #fff7e6); display: flex; align-items: center; justify-content: center; font-size: 28px; flex-shrink: 0; line-height: 1; }
.synth-info { flex: 1; min-width: 0; }
.synth-name { font-size: var(--font-size-md, 14px); font-weight: var(--font-weight-bold, 700); color: var(--text-primary, #1a1a2e); margin-bottom: 4px; }
.synth-tags-row { display: flex; gap: 4px; flex-wrap: wrap; }
.synth-role-tag, .synth-builtin-tag { margin: 0; font-size: 11px; line-height: 18px; padding: 0 6px; border: none; }
.synth-section { display: flex; flex-direction: column; gap: 6px; }
.synth-section-title { font-size: var(--font-size-xs, 11px); font-weight: var(--font-weight-semibold, 600); color: var(--text-muted, #8c8c8c); letter-spacing: 0.3px; }
.synth-desc { font-size: var(--font-size-sm, 13px); color: var(--text-primary, #1a1a2e); line-height: 1.6; }
.synth-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.synth-tag { margin: 0; font-size: 11px; line-height: 18px; padding: 0 6px; }
.synth-action-block { margin-top: var(--space-md, 12px); padding-top: var(--space-md, 12px); border-top: 1px solid var(--border-light, #f0f0f0); display: flex; flex-direction: column; gap: var(--space-xs, 4px); }
.synth-action-hint { font-size: var(--font-size-xs, 11px); color: var(--text-muted, #8c8c8c); line-height: 1.5; text-align: center; }

/* ── 工作台：流水线与深化工作区 ── */
.pipeline-filter { margin-bottom: 4px; }
.pipeline-card :deep(.ant-table) { background: transparent; }
.cand-name { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.cand-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.owner-name { font-size: 13px; color: var(--text-primary); }
.role-hint { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.scheme-empty { color: var(--text-muted); }
.action-link { padding: 0 4px; }

.workspace-card :deep(.ant-card-body) { padding-top: 16px; }
.candidate-info { padding-bottom: 16px; border-bottom: 1px solid var(--border-light); margin-bottom: 16px; }
.cand-head { display: flex; gap: 16px; align-items: flex-start; }
.cand-icon { flex-shrink: 0; }
.cand-meta { flex: 1; min-width: 0; }
.cand-title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin-bottom: 8px; }
.cand-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.cand-tags :deep(.ant-tag) { margin: 0; }
.cand-smiles { font-size: 13px; color: var(--text-primary); word-break: break-all; }
.cand-smiles code { font-family: 'JetBrains Mono', monospace; background: var(--light-bg); padding: 2px 6px; border-radius: 4px; }
.deepen-actions { display: flex; align-items: center; gap: 12px; margin-top: 16px; flex-wrap: wrap; }
.action-hint { font-size: 12px; color: var(--text-muted); }

.scheme-list { display: flex; flex-direction: column; gap: 16px; }
.scheme-block { border: 1px solid var(--border-light); border-radius: var(--radius-lg, 8px); padding: 16px; }
.scheme-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.scheme-id { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.scheme-id code { font-family: 'JetBrains Mono', monospace; background: var(--light-bg); padding: 2px 6px; border-radius: 4px; font-size: 12px; }
.scheme-label { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.scheme-meta { display: flex; gap: 12px; font-size: 12px; }
.scheme-routes { margin-bottom: 8px; }
.scheme-route { border: 1px solid var(--border-light); border-radius: var(--radius-md, 6px); padding: 12px; margin-bottom: 12px; }
.route-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.route-stats { display: flex; gap: 16px; margin-bottom: 8px; }
.stat { display: flex; flex-direction: column; gap: 2px; }
.stat .num { font-weight: 600; color: var(--text-primary); }
.route-dft { display: flex; align-items: center; gap: 8px; font-size: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.route-steps :deep(.ant-collapse-header) { padding: 6px 0 !important; font-size: 12px; }
.scheme-empty-hint { font-size: 13px; color: var(--text-muted); padding: 8px 0; }

.evidence-block { margin-top: 8px; border-top: 1px dashed var(--border-light); padding-top: 12px; }
.evidence-title { font-size: 13px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.evidence-list { display: flex; flex-direction: column; gap: 6px; }
.evidence-item { display: flex; align-items: center; gap: 8px; font-size: 12px; flex-wrap: wrap; }
.evidence-item :deep(.ant-tag) { margin: 0; }
.ev-cap { font-weight: 600; color: var(--text-primary); }
.ev-tool { font-family: 'JetBrains Mono', monospace; }
.ev-detail { font-size: 11px; }

@media (max-width: 1100px) {
  .synthesis-layout { flex-direction: column; }
  .synth-agent-panel { width: 100%; }
}

@media (prefers-reduced-motion: reduce) {
  .result-section { animation: none; }
}
</style>