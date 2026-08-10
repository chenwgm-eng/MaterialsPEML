<template>
  <div class="temp-prediction">
    <!-- 说明条：与「临时逆合成规划」顶部样式对齐，浅色信息提示 -->
    <div class="prediction-tip">
      <InfoCircleOutlined />
      <span>该工具用于研发人员对任一化学式/SMILES做临时性质预测与初步评估，不绑定候选流水线。</span>
    </div>

    <!-- 来自材料发现的携带信息 -->
    <a-alert v-if="carryInfo" type="info" show-icon class="carry-alert">
      <template #message>来自材料发现的目标：{{ carryInfo }}</template>
    </a-alert>

    <!-- P3-2：研发工作台派生上下文横幅 -->
    <ResearchContextBanner />

    <!-- 两列布局：左侧输入表单 + 右侧 Agent 信息面板 -->
    <div class="prediction-layout">
      <div class="prediction-main">
    <!-- 输入表单 -->
    <a-card class="app-card" :bordered="false">
      <div class="mode-switch">
        <a-radio-group v-model:value="predictMode" button-style="solid">
          <a-radio-button value="standard">标准预测</a-radio-button>
          <a-radio-button value="cross_scale">跨尺度建模</a-radio-button>
        </a-radio-group>
      </div>
      <div v-if="predictMode === 'cross_scale'">
        <a-form class="discovery-form">
          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item label="材料类型">
                <a-radio-group v-model:value="crossScaleForm.material_type">
                  <a-radio-button value="crystal">晶体</a-radio-button>
                  <a-radio-button value="molecule">分子</a-radio-button>
                </a-radio-group>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item v-if="crossScaleForm.material_type === 'crystal'" label="化学式">
                <a-input v-model:value="crossScaleForm.formula" name="formula" autocomplete="off" placeholder="例如 LiCoO2…" allow-clear />
              </a-form-item>
              <a-form-item v-else label="SMILES">
                <a-input v-model:value="crossScaleForm.smiles" name="smiles" autocomplete="off" placeholder="例如 CC(=O)O…" allow-clear />
              </a-form-item>
            </a-col>
          </a-row>
          <a-form-item label="预测模型">
            <a-select
              v-model:value="crossScaleForm.model_type"
              placeholder="选择预测模型（与系统设置同步）"
              :loading="modelCatalogLoading"
              allow-clear
            >
              <a-select-option
                v-for="m in availableCrossScaleModels"
                :key="m.id || m.name"
                :value="m.id || m.name"
                :disabled="m.enabled === false"
              >
                {{ m.name || m.id }}
                <span v-if="m.enabled === false" class="model-disabled-hint">（未启用）</span>
              </a-select-option>
            </a-select>
            <span class="input-hint">灰色项为系统设置中未启用的模型</span>
          </a-form-item>
          <a-form-item label="建模尺度">
            <a-checkbox-group v-model:value="crossScaleForm.scales">
              <a-checkbox value="molecular">分子尺度</a-checkbox>
              <a-checkbox value="reaction">反应尺度</a-checkbox>
              <a-checkbox value="continuum">连续介质尺度</a-checkbox>
            </a-checkbox-group>
          </a-form-item>
        </a-form>
      </div>
      <a-tabs v-else v-model:activeKey="materialType">
        <a-tab-pane key="crystal">
          <template #tab>
            <ExperimentOutlined /> 晶体材料
          </template>
          <a-form class="discovery-form">
            <a-form-item label="化学式">
              <a-input v-model:value="crystalForm.formula" name="formula" autocomplete="off" placeholder="例如 LiCoO2…" allow-clear />
              <div class="template-chips">
                <span class="chip-label">模板：</span>
                <a-tag
                  v-for="t in crystalTemplates"
                  :key="t"
                  class="template-chip"
                  role="button"
                  tabindex="0"
                  @click="crystalForm.formula = t"
                  @keydown.enter.prevent="crystalForm.formula = t"
                >
                  {{ t }}
                </a-tag>
              </div>
            </a-form-item>
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="优化模式">
                  <a-radio-group v-model:value="crystalForm.optimize_mode">
                    <a-radio-button value="single">单目标</a-radio-button>
                    <a-radio-button value="multi">多目标优化</a-radio-button>
                  </a-radio-group>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="候选数量">
                  <a-input-number v-model:value="crystalForm.num_candidates" :min="1" :max="20" style="width: 100%" />
                </a-form-item>
              </a-col>
            </a-row>
            <!-- 单目标 -->
            <a-form-item v-if="crystalForm.optimize_mode === 'single'" label="目标属性">
              <a-select v-model:value="crystalForm.target_property" :options="propertyOptions" />
            </a-form-item>
            <!-- 多目标 -->
            <div v-else>
              <a-form-item label="目标属性集">
                <a-select
                  v-model:value="crystalForm.multi_objective_props"
                  mode="multiple"
                  placeholder="选择多个目标属性"
                  :options="multiObjectiveOptions"
                  style="width: 100%"
                />
                <span class="input-hint">支持多目标帕累托加权优化</span>
              </a-form-item>
              <a-collapse
                v-if="crystalForm.multi_objective_props.length > 0"
                :bordered="false"
                :default-active-key="[]"
                class="mo-collapse"
              >
                <a-collapse-panel key="mo" header="多目标优化配置（权重 / 方向 / 约束）">
                  <div class="multi-objective-editor">
                    <div class="mo-header">
                      <span class="mo-col-prop">属性</span>
                      <span class="mo-col-weight">权重</span>
                      <span class="mo-col-dir">方向</span>
                      <span class="mo-col-min">最小约束</span>
                      <span class="mo-col-max">最大约束</span>
                    </div>
                    <div v-for="prop in crystalForm.multi_objective_props" :key="prop" class="mo-row">
                      <span class="mo-col-prop">{{ multiObjectiveLabel(prop) }}</span>
                      <span class="mo-col-weight">
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
                </a-collapse-panel>
              </a-collapse>
            </div>
          </a-form>
        </a-tab-pane>

        <a-tab-pane key="polymer">
          <template #tab>
            <ExperimentOutlined /> 聚合物
          </template>
          <a-form class="discovery-form">
            <a-form-item label="SMILES">
              <a-input v-model:value="polymerForm.smiles" name="smiles" autocomplete="off" placeholder="例如 CC(=O)O…" allow-clear />
              <div class="template-chips">
                <span class="chip-label">模板：</span>
                <a-tag
                  v-for="t in polymerTemplates"
                  :key="t"
                  class="template-chip"
                  role="button"
                  tabindex="0"
                  @click="polymerForm.smiles = t"
                  @keydown.enter.prevent="polymerForm.smiles = t"
                >
                  {{ t }}
                </a-tag>
              </div>
            </a-form-item>
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="候选数量">
                  <a-input-number v-model:value="polymerForm.num_candidates" :min="1" :max="20" style="width: 100%" />
                </a-form-item>
              </a-col>
            </a-row>
          </a-form>
        </a-tab-pane>
      </a-tabs>
    </a-card>
      </div>

      <!-- 右侧：材料发现 Agent 信息面板 + 执行按钮 -->
      <aside class="predict-agent-panel">
        <a-spin :spinning="agentLoading">
          <div v-if="selectedAgent" class="predict-agent-card">
            <div class="predict-panel-title">执行智能体</div>

            <!-- 多 Agent 时：下拉切换 -->
            <div v-if="capableAgents.length > 1" class="agent-select-block">
              <a-select
                v-model:value="selectedAgentId"
                size="small"
                style="width: 100%"
                @change="onAgentChange"
              >
                <a-select-option v-for="a in capableAgents" :key="a.id" :value="a.id">
                  {{ a.name }}
                </a-select-option>
              </a-select>
            </div>

            <!-- 头像 + 名称 + 角色标签 -->
            <div class="predict-head">
              <div class="predict-avatar">
                <component :is="selectedAgentIcon" aria-hidden="true" />
              </div>
              <div class="predict-info">
                <div class="predict-name">{{ selectedAgent.name || '材料发现' }}</div>
                <div class="predict-tags-row">
                  <a-tag color="green" class="predict-role-tag">材料发现</a-tag>
                  <a-tag v-if="selectedAgent.is_builtin" color="default" class="predict-builtin-tag">内置</a-tag>
                </div>
              </div>
            </div>

            <!-- 职责描述 -->
            <div class="predict-section">
              <div class="predict-section-title">职责描述</div>
              <div class="predict-desc">{{ selectedAgent.description || '基于化学式 / SMILES 与目标属性生成候选材料并预测性质' }}</div>
            </div>

            <!-- 专长 -->
            <div v-if="selectedAgent.expertise?.length" class="predict-section">
              <div class="predict-section-title">专长</div>
              <div class="predict-tags">
                <a-tag v-for="e in selectedAgent.expertise" :key="e" size="small" class="predict-tag">{{ e }}</a-tag>
              </div>
            </div>

            <!-- 基本信息 -->
            <div class="predict-section">
              <div class="predict-section-title">基本信息</div>
              <a-descriptions size="small" :column="1" :colon="false" class="predict-desc-list">
                <a-descriptions-item label="模型">{{ selectedAgent.llm_model || '—' }}</a-descriptions-item>
                <a-descriptions-item label="状态">
                  <a-tag v-if="selectedAgent.is_builtin" color="blue" size="small">内置可用</a-tag>
                  <span v-else>{{ selectedAgent.status || '—' }}</span>
                </a-descriptions-item>
                <a-descriptions-item label="工具数">{{ selectedAgent.tools?.length || 0 }}</a-descriptions-item>
              </a-descriptions>
            </div>

            <!-- Agent 执行按钮：根据当前模式调用不同函数 -->
            <div class="predict-action-block">
              <DisabledButton
                v-if="predictMode === 'cross_scale'"
                type="primary"
                block
                :loading="loading"
                :disabled="crossScaleForm.scales.length === 0 || !canRunCrossScale"
                disabled-reason="请先输入化学式或 SMILES，并至少选择一个建模尺度"
                @click="runCrossScale"
              >
                <LineChartOutlined /> 开始建模
              </DisabledButton>
              <a-button
                v-else
                type="primary"
                block
                :loading="loading"
                :disabled="!canRunStandard"
                @click="onPredict"
              >
                <LineChartOutlined /> 开始预测
              </a-button>
              <div v-if="loading" class="predict-action-hint">
                智能体正在生成候选材料并预测性质，通常需要 10-30 秒
              </div>
              <div v-else-if="predictMode === 'cross_scale' && !canRunCrossScale" class="predict-action-hint">
                请先输入化学式或 SMILES，并至少选择一个建模尺度
              </div>
              <div v-else-if="predictMode === 'standard' && !canRunStandard" class="predict-action-hint">
                {{ standardHint }}
              </div>
            </div>
          </div>
          <EmptyState
            v-else-if="!agentLoading"
            type="data"
            description="暂无材料发现 Agent"
          />
        </a-spin>
      </aside>
    </div>

    <!-- 结果区 -->
    <SmartLoading
      v-if="predictMode === 'standard' && loading && !hasResults"
      :loading="true"
      skeleton-type="table"
      tip="正在预测，请稍候..."
      show-cancel
      @cancel="onCancelPredict"
    />
    <template v-else-if="predictMode === 'standard'">
      <a-card v-if="hasResults" class="app-card" :bordered="false">
        <template #title>
          <div class="result-header">
            <span>预测结果</span>
            <a-tag color="blue">{{ candidates.length }} 个候选材料</a-tag>
            <a-tooltip :title="selected.length === 0 ? '请先勾选候选材料' : ''">
              <span class="tt-btn-wrap">
                <a-button size="small" :disabled="selected.length === 0" @click="sendToSynthesis">发送到合成</a-button>
              </span>
            </a-tooltip>
            <a-tooltip :title="selected.length === 0 ? '请先勾选候选材料' : ''">
              <span class="tt-btn-wrap">
                <a-button size="small" :disabled="selected.length === 0" @click="sendToExperiment">发送到实验</a-button>
              </span>
            </a-tooltip>
            <a-tooltip :title="selected.length === 0 ? '请先勾选候选材料' : ''">
              <span class="tt-btn-wrap">
                <a-button size="small" :disabled="selected.length === 0" @click="sendToFormula">发送到配方</a-button>
              </span>
            </a-tooltip>
            <a-tooltip :title="selected.length === 0 ? '请先勾选候选材料' : ''">
              <span class="tt-btn-wrap">
                <a-button size="small" type="primary" ghost :disabled="selected.length === 0" :loading="availabilityLoading" @click="checkAvailability">检查原料可得性</a-button>
              </span>
            </a-tooltip>
            <a-tooltip :title="selected.length === 0 ? '请先勾选候选材料' : ''">
              <span class="tt-btn-wrap">
                <a-button size="small" type="primary" :disabled="selected.length === 0" @click="promptFeedbackToMaterialDB">反哺到物料库</a-button>
              </span>
            </a-tooltip>
          </div>
        </template>
        <a-tabs v-if="hasMultiObjective" size="small" class="chart-tabs">
          <a-tab-pane key="pareto" tab="帕累托前沿">
            <ParetoChart :candidates="candidatesWithObjectives" @select="onChartSelect" />
          </a-tab-pane>
          <a-tab-pane key="radar" tab="雷达图">
            <RadarChart :candidates="candidatesWithObjectives" />
          </a-tab-pane>
        </a-tabs>

        <!-- 视图切换：候选卡片（默认）/ 表格 -->
        <div class="result-view-switch">
          <a-radio-group v-model:value="resultView" size="small" button-style="solid">
            <a-radio-button value="card">候选卡片</a-radio-button>
            <a-radio-button value="table">表格视图</a-radio-button>
          </a-radio-group>
        </div>

        <!-- 候选卡片流（对齐临时逆合成结果卡片风格：结构图 + 关键属性 + 可展开明细 + 单项操作） -->
        <div v-if="resultView === 'card'" class="candidate-card-grid">
          <div
            v-for="(c, idx) in candidates"
            :key="cardKey(c, idx)"
            class="c-card"
            :class="{ 'is-checked': isCardChecked(c, idx) }"
          >
            <div class="c-card-head">
              <StructureView
                :smiles="c.smiles"
                :formula="c.formula"
                :space-group="c.space_group"
                :structure-type="c.structure_type"
                :kind="materialType === 'polymer' ? 'molecule' : 'crystal'"
                :size="72"
              />
              <div class="c-card-title">
                <div class="c-name">{{ c.name || c.formula || c.smiles || '未命名' }}</div>
                <div class="c-formula">{{ c.formula }}</div>
              </div>
              <a-checkbox
                :checked="isCardChecked(c, idx)"
                @change="(e) => onCardCheck(c, idx, e.target.checked)"
              >选择</a-checkbox>
            </div>
            <div class="c-metrics">
              <span v-if="c.band_gap != null" class="c-metric"><span class="c-label">带隙</span><b class="c-value">{{ fmtVal(c.band_gap) }}</b></span>
              <span v-if="c.formation_energy != null" class="c-metric"><span class="c-label">形成能</span><b class="c-value">{{ fmtVal(c.formation_energy) }}</b></span>
              <span v-if="c.ionic_conductivity_estimate != null" class="c-metric"><span class="c-label">电导率</span><b class="c-value">{{ fmtVal(c.ionic_conductivity_estimate) }}</b></span>
              <span v-if="c.multi_objective_score != null" class="c-metric"><span class="c-label">综合评分</span><b class="c-value">{{ (c.multi_objective_score * 100).toFixed(0) }}%</b></span>
            </div>
            <a-collapse :bordered="false" class="c-collapse">
              <a-collapse-panel key="detail" :header="`属性明细（${detailEntries(c).length}）`">
                <a-descriptions :column="1" size="small" bordered>
                  <a-descriptions-item v-for="(e, i) in detailEntries(c)" :key="i" :label="e.label">{{ e.value }}</a-descriptions-item>
                </a-descriptions>
              </a-collapse-panel>
            </a-collapse>
            <div class="c-actions">
              <a-button size="small" type="primary" ghost @click="sendToSynthesis(c)">发送合成</a-button>
              <a-button size="small" type="primary" ghost @click="sendToExperiment(c)">发送实验</a-button>
              <a-button size="small" type="primary" ghost @click="sendToFormula(c)">发送配方</a-button>
              <!-- 材料设计模块重组：临时预测结果转正为候选材料 -->
              <a-button size="small" type="primary" @click="openPromoteModal(c, idx)">创建为候选材料</a-button>
            </div>
          </div>
        </div>

        <!-- 表格视图（保留，适合多候选对比/批量选择） -->
        <CandidateTable v-else :data="candidates" :loading="loading" :type="materialType" :selectable="true" :selected="selectedKeys" :moObjectives="moObjectivesForTable" @select="onSelect" />
      </a-card>

      <a-card v-if="hasResults" class="app-card" :bordered="false">
        <template #title>预测性质条形图（按 {{ chartPropertyLabel }} 排序）</template>
        <ResultChart type="bar" :data="chartData" x-key="x" y-key="y" :height="300" />
      </a-card>

      <a-card v-else-if="predictError" class="app-card empty-card" :bordered="false">
        <EmptyAction title="预测失败" :description="predictError" actionText="重试" @action="onPredict" />
      </a-card>

      <a-card v-else class="app-card empty-card" :bordered="false">
        <EmptyState type="data" description="输入参数并点击「开始预测」查看预测结果" />
      </a-card>
    </template>

    <!-- 跨尺度建模结果 -->
    <a-spin v-if="predictMode === 'cross_scale'" :spinning="loading">
      <a-card v-if="crossScaleResult" class="app-card" :bordered="false">
        <template #title>跨尺度建模结果</template>
        <a-tabs v-model:activeKey="crossScaleTab" size="small">
          <a-tab-pane v-if="crossScaleResult.molecular" key="molecular" tab="分子尺度">
            <a-table
              :columns="molPropertyColumns"
              :data-source="crossScaleResult.molecular.properties || []"
              size="small"
              :pagination="false"
              :row-key="(r) => r.name"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'confidence'">
                  <a-progress :percent="Math.round((record.confidence || 0) * 100)" size="small" />
                </template>
              </template>
            </a-table>
          </a-tab-pane>

          <a-tab-pane v-if="crossScaleResult.reaction" key="reaction" tab="反应尺度">
            <a-descriptions title="反应路径" size="small" :column="2" bordered>
              <a-descriptions-item label="目标">{{ crossScaleResult.reaction.pathway?.target || '-' }}</a-descriptions-item>
              <a-descriptions-item label="步骤数">{{ crossScaleResult.reaction.pathway?.num_steps ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="可行性评分">{{ fmtVal(crossScaleResult.reaction.pathway?.feasibility_score) }}</a-descriptions-item>
              <a-descriptions-item label="总产率">
                <a-tag v-if="crossScaleResult.reaction.yield != null" color="green">
                  {{ (Number(crossScaleResult.reaction.yield) * 100).toFixed(1) }}%
                </a-tag>
                <span v-else>-</span>
              </a-descriptions-item>
            </a-descriptions>
            <a-table
              :columns="kineticsColumns"
              :data-source="crossScaleResult.reaction.kinetics || []"
              size="small"
              :pagination="false"
              :row-key="(r) => r.step"
              style="margin-top: 16px"
            />
          </a-tab-pane>

          <a-tab-pane v-if="crossScaleResult.continuum" key="continuum" tab="连续介质尺度">
            <a-row :gutter="16">
              <a-col :span="8">
                <a-card size="small" title="电化学">
                  <p v-for="(v, k) in (crossScaleResult.continuum.electrochemical || {})" :key="k" class="kv-line">
                    <span class="kv-label">{{ continuumLabels[k] || k }}</span>
                    <strong>{{ fmtVal(v) }}</strong>
                  </p>
                </a-card>
              </a-col>
              <a-col :span="8">
                <a-card size="small" title="热学">
                  <p v-for="(v, k) in (crossScaleResult.continuum.thermal || {})" :key="k" class="kv-line">
                    <span class="kv-label">{{ continuumLabels[k] || k }}</span>
                    <strong>{{ fmtVal(v) }}</strong>
                  </p>
                </a-card>
              </a-col>
              <a-col :span="8">
                <a-card size="small" title="力学">
                  <p v-for="(v, k) in (crossScaleResult.continuum.mechanical || {})" :key="k" class="kv-line">
                    <span class="kv-label">{{ continuumLabels[k] || k }}</span>
                    <strong>{{ fmtVal(v) }}</strong>
                  </p>
                </a-card>
              </a-col>
            </a-row>
          </a-tab-pane>

          <a-tab-pane v-if="crossScaleResult.coupled" key="coupled" tab="耦合分析">
            <a-alert v-if="crossScaleResult.coupled.summary" :message="crossScaleResult.coupled.summary" type="info" show-icon style="margin-bottom: 16px" />
            <a-list :data-source="crossScaleResult.coupled.correlations || []" item-layout="horizontal">
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-list-item-meta>
                    <template #title>
                      <a-tag color="blue">{{ item.from_scale }}</a-tag>
                      →
                      <a-tag color="blue">{{ item.to_scale }}</a-tag>
                      <span style="margin-left: 8px">{{ item.property }}</span>
                    </template>
                    <template #description>{{ item.description }}</template>
                  </a-list-item-meta>
                  <template #actions>
                    <a-tag :color="item.correlation === 'positive' ? 'green' : 'orange'">
                      {{ item.correlation === 'positive' ? '正相关' : '负相关' }}
                    </a-tag>
                  </template>
                </a-list-item>
              </template>
            </a-list>
          </a-tab-pane>
        </a-tabs>
      </a-card>
      <a-card v-else class="app-card empty-card" :bordered="false">
        <EmptyState type="data" description="选择材料与尺度，点击「开始建模」查看跨尺度结果" />
      </a-card>
    </a-spin>

    <a-modal v-model:open="confirmVisible" :title="confirmTitle" @ok="onConfirmOk" @cancel="confirmVisible = false">
      <p>{{ confirmContent }}</p>
    </a-modal>

    <!-- 原料可得性检查抽屉 -->
    <a-drawer
      :open="availabilityVisible"
      title="原料可得性检查结果"
      placement="right"
      width="900px"
      :footer="null"
      @update:open="(v) => (availabilityVisible = v)"
    >
      <a-spin :spinning="availabilityLoading">
        <a-alert
          v-if="availabilityResults.length === 0 && !availabilityLoading"
          type="info"
          message="未选择候选材料或未匹配到任何原料"
          show-icon
        />
        <div v-for="res in availabilityResults" :key="res.candidate_id" class="availability-block">
          <div class="availability-header">
            <span class="candidate-name">{{ res.name || res.formula || res.smiles || res.candidate_id }}</span>
            <a-tag :color="statusColor(res.status)">{{ statusLabel(res.status) }}</a-tag>
            <span v-if="res.cost_estimate" class="cost-summary">
              预估成本：¥{{ res.cost_estimate.total_cost?.toFixed(2) }}
              <span v-if="res.cost_estimate.shortage > 0" class="shortage">
                （缺口 {{ res.cost_estimate.shortage.toFixed(2) }} {{ massUnit }}）
              </span>
            </span>
          </div>
          <a-table
            v-if="res.matched_materials && res.matched_materials.length > 0"
            :columns="availabilityColumns"
            :data-source="res.matched_materials"
            size="small"
            :pagination="false"
            :row-key="(r) => r.material_id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'category'">
                <a-tag>{{ industrialCategoryLabel(record.category) }}</a-tag>
              </template>
              <template v-if="column.key === 'in_stock'">
                <a-tag v-if="record.inventory_quantity >= 1" color="green">库存 {{ record.inventory_quantity }} {{ massUnit }}</a-tag>
                <a-tag v-else color="orange">库存不足</a-tag>
              </template>
            </template>
          </a-table>
          <EmptyState v-else type="data" description="物料库中无匹配原料，需全部新采购" />
        </div>
      </a-spin>
    </a-drawer>

    <!-- 材料设计模块重组：「创建为候选材料」转正弹窗 -->
    <a-modal
      v-model:open="promoteVisible"
      title="创建为候选材料"
      :confirm-loading="promoteLoading"
      ok-text="确认创建"
      cancel-text="取消"
      @ok="doPromote"
    >
      <p class="promote-desc">
        将该临时预测结果写入所选任务下的候选列表，继承已计算的属性预测数据（无需重新预测）。
      </p>
      <a-form layout="vertical">
        <a-form-item label="所属项目" required>
          <a-select
            v-model:value="promoteProjectId"
            :options="promoteProjectOptions"
            placeholder="请选择项目"
            show-search
            option-filter-prop="label"
            allow-clear
            @change="onPromoteProjectChange"
          />
        </a-form-item>
        <a-form-item label="所属任务" required>
          <a-select
            v-model:value="promoteTaskId"
            :options="promoteTaskOptions"
            :placeholder="promoteProjectId ? '请选择任务' : '请先选择项目'"
            :disabled="!promoteProjectId"
            show-search
            option-filter-prop="label"
            allow-clear
          />
        </a-form-item>
      </a-form>
      <div v-if="promoteTarget" class="promote-target">
        转正对象：<b>{{ promoteTarget.name || promoteTarget.formula || promoteTarget.smiles || '未命名' }}</b>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, h, onMounted, onBeforeUnmount, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import { InfoCircleOutlined, ExperimentOutlined, LineChartOutlined } from '@ant-design/icons-vue'
import { discoverCrystal, discoverPolymer } from '@/api/discovery'
import { getOptions, crossScalePredict } from '@/api/properties'
import { checkMaterialsAvailability } from '@/api/rawMaterials'
import { getModelCatalog } from '@/api/system'
import { createMaterialRequest } from '@/api/materialRequests'
import { listAgents } from '@/api/agents'
import { promoteFromTemporary } from '@/api/candidates'
import { listProjects, listProjectTasks } from '@/api/projects'
import client from '@/api/client'
import { formatSci } from '@/utils/format'
import { useMdmDict, useUnitSymbols } from '@/utils/mdmDict'
import { resolveAgentIcon } from '@/utils/agentAvatar'
import { industrialCategoryLabel } from '@/constants/materialTypes'
import { DEFAULT_MULTI_OBJECTIVE_CONFIG, MULTI_OBJECTIVE_OPTIONS } from '@/constants/objectiveConfig'
import DisabledButton from '@/components/DisabledButton.vue'
import ScientificNotation from '@/components/ScientificNotation.vue'
import CandidateTable from '@/components/CandidateTable.vue'
import ResultChart from '@/components/ResultChart.vue'
import ParetoChart from '@/components/ParetoChart.vue'
import RadarChart from '@/components/RadarChart.vue'
import ResearchContextBanner from '@/components/ResearchContextBanner.vue'
import EmptyState from '@/components/EmptyState.vue'
import EmptyAction from '@/components/EmptyAction.vue'
import SmartLoading from '@/components/SmartLoading.vue'
import StructureView from '@/components/StructureView.vue'

const emit = defineEmits(['promoted'])

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const materialType = ref('crystal')
const candidates = ref([])
const selected = ref([])
const selectedKeys = ref([])
// 预测失败提示（超时/网络/服务端错误），用于结果区展示"失败 + 重试"卡片
const predictError = ref('')

// 取消等待预测结果（仅隐藏骨架屏，后端预测仍会完成并填充数据）
function onCancelPredict() {
  loading.value = false
}

// ── 材料发现 Agent 信息（右侧面板展示） ──
const capableAgents = ref([])
const selectedAgentId = ref('')
const agentLoading = ref(false)

const selectedAgent = computed(() =>
  capableAgents.value.find((a) => a.id === selectedAgentId.value) || capableAgents.value[0] || null
)

const selectedAgentIcon = computed(() => resolveAgentIcon(selectedAgent.value?.avatar))

async function loadCapableAgents() {
  agentLoading.value = true
  try {
    const res = await listAgents()
    const list = Array.isArray(res) ? res : (res?.agents || [])
    // 优先匹配 role === 'material_discovery'，回退到 id 包含 material_discovery
    const byRole = list.filter((a) => a.role === 'material_discovery')
    const matched = byRole.length
      ? byRole
      : list.filter((a) => a.id && a.id.includes('material_discovery'))
    capableAgents.value = matched.length ? matched : []
    if (capableAgents.value.length) {
      selectedAgentId.value = capableAgents.value[0].id
    }
  } catch {
    capableAgents.value = []
  } finally {
    agentLoading.value = false
  }
}

function onAgentChange(id) {
  selectedAgentId.value = id
}

// 标准预测可执行条件：晶体需化学式，聚合物需 SMILES
const canRunStandard = computed(() => {
  if (predictMode.value !== 'standard') return false
  if (materialType.value === 'crystal') return !!crystalForm.formula.trim()
  return !!polymerForm.smiles.trim()
})

const standardHint = computed(() => {
  if (materialType.value === 'crystal') return '请先输入化学式'
  return '请先输入 SMILES'
})

// 跨尺度建模可执行条件：需化学式或 SMILES
const canRunCrossScale = computed(() => {
  if (predictMode.value !== 'cross_scale') return false
  return !!(crossScaleForm.formula.trim() || crossScaleForm.smiles.trim())
})

// 从 MDM 加载单位符号（失败时 computed 使用默认单位兜底）
const { symbols: unitSymbols, load: loadUnitSymbols } = useUnitSymbols()
const massUnit = computed(() => unitSymbols.value.mass || 'kg')
const voltageUnit = computed(() => unitSymbols.value.voltage || 'V')
const capUnit = computed(() => unitSymbols.value.specific_capacity || 'mAh/g')
const densityUnit = computed(() => unitSymbols.value.density || 'g/cm³')
const activationEnergyUnit = computed(() => unitSymbols.value.activation_energy || 'kJ/mol')
const rateConstantUnit = computed(() => unitSymbols.value.rate_constant || '1/s')
const temperatureDeltaUnit = computed(() => unitSymbols.value.temperature_delta || 'K')
const energyDensityUnit = computed(() => unitSymbols.value.energy_density || 'Wh/kg')
const powerDensityUnit = computed(() => unitSymbols.value.power_density || 'W/kg')
const thermalConductivityUnit = computed(() => unitSymbols.value.thermal_conductivity || 'W/mK')
const heatGenerationUnit = computed(() => unitSymbols.value.heat_generation || 'W/m³')
const modulusUnit = computed(() => unitSymbols.value.modulus || 'GPa')

// 原料可得性检查
const availabilityVisible = ref(false)
const availabilityLoading = ref(false)
const availabilityResults = ref([])
const availabilityColumns = computed(() => [
  { title: '物料编码', dataIndex: 'material_id', key: 'material_id', width: 100 },
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '分类', dataIndex: 'category', key: 'category', width: 100 },
  { title: `库存(${massUnit.value})`, dataIndex: 'inventory_quantity', key: 'inventory_quantity', width: 90, align: 'right' },
  { title: `单价(元/${massUnit.value})`, dataIndex: 'unit_cost', key: 'unit_cost', width: 100, align: 'right' },
  { title: '供应商', dataIndex: 'supplier', key: 'supplier', width: 120 },
  { title: '可得性', key: 'in_stock', width: 110 },
])

const crystalForm = reactive({
  formula: '',
  target_property: 'ionic_conductivity',
  num_candidates: 5,
  optimize_mode: 'single', // 'single' | 'multi'
  multi_objective_props: [],
})

const polymerForm = reactive({
  smiles: '',
  num_candidates: 5,
})

// 跨尺度建模
const predictMode = ref('standard')
const crossScaleForm = reactive({
  material_type: 'crystal',
  formula: '',
  smiles: '',
  scales: ['molecular', 'reaction', 'continuum'],
  model_type: undefined,
})
// 预测模型目录（与系统设置同步）：从后端 getModelCatalog 拉取，enabled=false 的模型灰色不可选
const modelCatalogLoading = ref(false)
const modelCatalogData = ref({ expert_models: [], dft_methods: { enabled: false } })
const availableCrossScaleModels = computed(() => {
  // 跨尺度建模支持全部模型类别（crystal/polymer/universal 等），
  // 仅排除后端明确标记不可用的项；enabled=false 的模型以下拉灰色方式展示（与系统设置同步）
  return modelCatalogData.value.expert_models || []
})
const crossScaleResult = ref(null)
const crossScaleTab = ref('molecular')
const molPropertyColumns = [
  { title: '属性', dataIndex: 'name', key: 'name' },
  { title: '值', dataIndex: 'value', key: 'value', align: 'right', customRender: ({ text }) => fmtVal(text) },
  { title: '单位', dataIndex: 'unit', key: 'unit', width: 80 },
  { title: '模型', dataIndex: 'model', key: 'model', width: 140 },
  { title: '置信度', key: 'confidence', width: 120 },
]
const kineticsColumns = computed(() => [
  { title: '步骤', dataIndex: 'step', key: 'step', width: 60 },
  { title: '反应类型', dataIndex: 'reaction_type', key: 'reaction_type' },
  { title: `活化能(${activationEnergyUnit.value})`, dataIndex: 'activation_energy', key: 'Ea', align: 'right', customRender: ({ text }) => h(ScientificNotation, { value: text, precision: 4 }) },
  { title: `速率常数(${rateConstantUnit.value})`, dataIndex: 'rate_constant', key: 'k', align: 'right', customRender: ({ text }) => h(ScientificNotation, { value: text, precision: 4 }) },
  { title: `温度(${temperatureDeltaUnit.value})`, dataIndex: 'temperature_kelvin', key: 'T', align: 'right', customRender: ({ text }) => h(ScientificNotation, { value: text, precision: 4 }) },
  { title: '步产率', dataIndex: 'step_yield', key: 'yield', align: 'right', customRender: ({ text }) => (Number(text) * 100).toFixed(1) + '%' },
])
const continuumLabels = computed(() => ({
  operating_voltage: `工作电压(${voltageUnit.value})`,
  theoretical_capacity: `理论容量(${capUnit.value})`,
  energy_density: `能量密度(${energyDensityUnit.value})`,
  power_density: `功率密度(${powerDensityUnit.value})`,
  thermal_conductivity: `热导率(${thermalConductivityUnit.value})`,
  heat_generation: `产热率(${heatGenerationUnit.value})`,
  max_temperature_rise: `最大温升(${temperatureDeltaUnit.value})`,
  elastic_modulus: `弹性模量(${modulusUnit.value})`,
  bulk_modulus: `体积模量(${modulusUnit.value})`,
  shear_modulus: `剪切模量(${modulusUnit.value})`,
  density: `密度(${densityUnit.value})`,
}))

// 数值安全格式化：数值型按 4 位有效数字截断，非数值原样展示
function fmtVal(v) {
  if (v == null || v === '') return '-'
  const n = Number(v)
  return Number.isFinite(n) ? formatSci(n, 4) : String(v)
}

// 多目标优化可选项与配置（与 Discovery.vue 对齐）
const multiObjectiveOptions = ref([...MULTI_OBJECTIVE_OPTIONS])
const multiObjectiveConfig = reactive({ ...DEFAULT_MULTI_OBJECTIVE_CONFIG })
function multiObjectiveLabel(key) {
  const opt = multiObjectiveOptions.find((o) => o.value === key)
  return opt ? opt.label : key
}

const LAST_FORMULA_KEY = 'battery_prediction:last_formula'
const LAST_SMILES_KEY = 'battery_prediction:last_smiles'

const crystalTemplates = ['LiCoO2', 'LiFePO4', 'LiNi0.8Mn0.1Co0.1O2']
const polymerTemplates = ['PEO', 'PVDF', 'PMMA']

const confirmVisible = ref(false)
const confirmTitle = ref('')
const confirmContent = ref('')
let confirmCallback = null

const propertyOptions = ref([])
const currentScenarioId = ref('')

const carryInfo = computed(() => {
  const parts = []
  if (route.query.goal) parts.push(`目标：${route.query.goal}`)
  if (route.query.formula) parts.push(`化学式 ${route.query.formula}`)
  if (route.query.smiles) parts.push(`SMILES ${route.query.smiles}`)
  if (route.query.scenario_id) parts.push(`场景 ${route.query.scenario_id}`)
  return parts.join(' · ')
})

// 目标属性 → 候选字段映射（晶体候选中离子电导率字段名带 _estimate 后缀）
const propertyFieldMap = {
  ionic_conductivity: 'ionic_conductivity_estimate',
  band_gap: 'band_gap',
  formation_energy: 'formation_energy',
}

const chartPropertyLabel = computed(() => {
  const opt = propertyOptions.value.find((o) => o.value === crystalForm.target_property)
  return opt ? opt.label : crystalForm.target_property
})

const hasResults = computed(() => candidates.value.length > 0)

// 属性 key → 候选字段映射
const FIELD_MAP = {
  ionic_conductivity: 'ionic_conductivity_estimate',
  band_gap: 'band_gap',
  formation_energy: 'formation_energy',
  stability: 'stability_score',
  energy_above_hull: 'energy_above_hull',
}

const hasMultiObjective = computed(() => {
  return crystalForm.optimize_mode === 'multi' && crystalForm.multi_objective_props.length > 0 && candidates.value.length > 0
})

const candidatesWithObjectives = computed(() => {
  if (!hasMultiObjective.value) return []
  const props_keys = crystalForm.multi_objective_props
  return candidates.value.map((c) => {
    const objectives = props_keys.map((key) => {
      const fieldName = FIELD_MAP[key] || key
      const opt = multiObjectiveOptions.find((o) => o.value === key)
      const cfg = multiObjectiveConfig[key] || { weight: 0.5, direction: 'maximize', min: null, max: null }
      return {
        name: opt ? opt.label : key,
        key,
        value: c[fieldName] ?? null,
        direction: cfg.direction,
        weight: cfg.weight,
        min: cfg.min,
        max: cfg.max,
      }
    })
    return { ...c, objectives }
  })
})

const moObjectivesForTable = computed(() => {
  if (!hasMultiObjective.value) return []
  return crystalForm.multi_objective_props.map((key) => {
    const opt = multiObjectiveOptions.find((o) => o.value === key)
    const cfg = multiObjectiveConfig[key] || {}
    return {
      key: FIELD_MAP[key] || key,
      name: opt ? opt.label : key,
      min: cfg.min,
      max: cfg.max,
    }
  })
})

const chartData = computed(() => {
  if (!hasResults.value) return []
  const field = propertyFieldMap[crystalForm.target_property] || crystalForm.target_property
  return candidates.value
    .map((c) => ({
      x: c.formula || c.name || c.smiles || '—',
      y: Number(c[field]),
    }))
    .filter((d) => d.y != null && !Number.isNaN(d.y))
    .sort((a, b) => b.y - a.y)
})

const optionsCtrl = new AbortController()

onMounted(async () => {
  // 从 MDM 加载单位符号（失败时 computed 使用默认单位兜底）
  await loadUnitSymbols()

  // 加载预测模型目录（与系统设置同步，enabled=false 的模型灰色不可选）
  modelCatalogLoading.value = true
  try {
    const res = await getModelCatalog()
    if (res?.data) {
      Object.assign(modelCatalogData.value, res.data)
    } else if (res) {
      Object.assign(modelCatalogData.value, res)
    }
  } catch (e) {
    // 后端不可达时保留空目录，下拉渲染为空
    console.warn('[TemporaryPrediction] 加载预测模型目录失败:', e)
  } finally {
    modelCatalogLoading.value = false
  }

  // 加载材料发现 Agent（右侧面板展示）
  loadCapableAgents()

  // P0-001：保存场景 ID，便于结果传递到下游
  if (route.query.scenario_id) {
    currentScenarioId.value = String(route.query.scenario_id)
  }

  // 根据 query 自动判断材料类型
  const qType = route.query.material_type
  const hasQuery = route.query.formula || route.query.smiles
  if (qType === 'polymer' || (!route.query.formula && route.query.smiles)) {
    materialType.value = 'polymer'
    polymerForm.smiles = route.query.smiles || ''
  } else {
    materialType.value = 'crystal'
    crystalForm.formula = route.query.formula || ''
  }

  // P3-2/P0-001：研发工作台派生上下文 —— 目标属性预填，避免重复录入
  if (route.query.target_property) {
    crystalForm.optimize_mode = 'single'
    crystalForm.target_property = String(route.query.target_property)
  }

  // URL 无参数时从 sessionStorage 兜底恢复（P3-2 派生上下文优先，跳过恢复避免混入陈旧输入）
  if (!hasQuery && route.query.from !== 'research') {
    const savedFormula = sessionStorage.getItem(LAST_FORMULA_KEY)
    const savedSmiles = sessionStorage.getItem(LAST_SMILES_KEY)
    if (materialType.value === 'polymer' && savedSmiles) {
      polymerForm.smiles = savedSmiles
    } else if (savedFormula) {
      crystalForm.formula = savedFormula
    }
  }

  // 加载目标属性选项
  try {
    const res = await getOptions({ usable_in: 'predictable' }, { signal: optionsCtrl.signal })
    propertyOptions.value = res.options
  } catch (e) {
    if (e.name === 'AbortError' || e.code === 'ERR_CANCELED' || e.message === 'canceled') return
    propertyOptions.value = [
      { label: '离子电导率', value: 'ionic_conductivity' },
      { label: '带隙', value: 'band_gap' },
      { label: '形成能', value: 'formation_energy' },
    ]
  }

  // 加载多目标属性选项（预测方法维度）
  const { dimensionOptions } = useMdmDict()
  try {
    const loaded = await dimensionOptions('data_source')
    multiObjectiveOptions.value = loaded.length ? loaded : [...multiObjectiveOptionsFallback]
    if (!loaded.length) {
      message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
    }
  } catch (e) {
    multiObjectiveOptions.value = [...multiObjectiveOptionsFallback]
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
})

onBeforeUnmount(() => {
  optionsCtrl.abort()
})

// 保存输入到 sessionStorage
watch(
  () => crystalForm.formula,
  (val) => {
    if (val) sessionStorage.setItem(LAST_FORMULA_KEY, val)
  }
)
watch(
  () => polymerForm.smiles,
  (val) => {
    if (val) sessionStorage.setItem(LAST_SMILES_KEY, val)
  }
)

// 周期表有效元素符号集合，用于诊断化学式解析中的无效元素（如 NMC811 → M）
const VALID_ELEMENTS = new Set([
  'H','He','Li','Be','B','C','N','O','F','Ne','Na','Mg','Al','Si','P','S','Cl','Ar',
  'K','Ca','Sc','Ti','V','Cr','Mn','Fe','Co','Ni','Cu','Zn','Ga','Ge','As','Se','Br','Kr',
  'Rb','Sr','Y','Zr','Nb','Mo','Tc','Ru','Rh','Pd','Ag','Cd','In','Sn','Sb','Te','I','Xe',
  'Cs','Ba','La','Ce','Pr','Nd','Pm','Sm','Eu','Gd','Tb','Dy','Ho','Er','Tm','Yb','Lu',
  'Hf','Ta','W','Re','Os','Ir','Pt','Au','Hg','Tl','Pb','Bi','Po','At','Rn',
  'Fr','Ra','Ac','Th','Pa','U','Np','Pu','Am','Cm','Bk','Cf','Es','Fm',
])

// 从化学式中提取元素符号（如 LiCoO2 → ['Li','Co','O']），同时诊断无效元素。
// 返回 { elements, invalidSymbols }；invalidSymbols 非空说明"化学式"不是合法式（如 NMC811 俗称）。
function parseElements(formula) {
  if (!formula) return { elements: [], invalidSymbols: [] }
  const matches = formula.match(/[A-Z][a-z]?/g) || []
  const elements = [...new Set(matches)]
  const invalidSymbols = elements.filter((e) => !VALID_ELEMENTS.has(e))
  return { elements, invalidSymbols }
}

function onSelect(rows, keys) {
  selected.value = rows
  selectedKeys.value = keys || []
}

// ── 结果视图切换：候选卡片（默认）/ 表格 ──
const resultView = ref('card')

function cardKey(c, idx) {
  return c.id || c.material_id || c.candidate_id || c.formula || c.smiles || c.name || `row-${idx}`
}

function isCardChecked(c, idx) {
  return selectedKeys.value.includes(cardKey(c, idx))
}

function onCardCheck(c, idx, checked) {
  const key = cardKey(c, idx)
  const rows = selected.value.slice()
  const keys = selectedKeys.value.slice()
  if (checked) {
    if (!keys.includes(key)) {
      keys.push(key)
      rows.push(c)
    }
  } else {
    const i = keys.indexOf(key)
    if (i >= 0) {
      keys.splice(i, 1)
      rows.splice(i, 1)
    }
  }
  selected.value = rows
  selectedKeys.value = keys
}

// 候选卡片的可展开属性明细（过滤空值，多目标综合评分转百分比）
function detailEntries(c) {
  const labels = {
    formula: '化学式', smiles: 'SMILES', space_group: '空间群', structure_type: '结构类型',
    band_gap: '带隙(eV)', formation_energy: '形成能(eV/atom)', ionic_conductivity_estimate: '电导率(S/cm)',
    stability_score: '稳定性', multi_objective_score: '综合评分', source: '来源',
  }
  const entries = []
  for (const [k, label] of Object.entries(labels)) {
    const v = c[k]
    if (v == null || v === '') continue
    if (k === 'multi_objective_score') entries.push({ label, value: (Number(v) * 100).toFixed(1) + '%' })
    else entries.push({ label, value: typeof v === 'number' ? fmtVal(v) : String(v) })
  }
  return entries
}

function onChartSelect(candidate) {
  selected.value = [candidate]
  const index = candidates.value.findIndex((c) =>
    (candidate.id && c.id === candidate.id) ||
    (candidate.material_id && c.material_id === candidate.material_id) ||
    (candidate.candidate_id && c.candidate_id === candidate.candidate_id) ||
    (candidate.formula && c.formula === candidate.formula) ||
    (candidate.smiles && c.smiles === candidate.smiles) ||
    (candidate.name && c.name === candidate.name)
  )
  const baseKey =
    candidate.id ||
    candidate.material_id ||
    candidate.candidate_id ||
    candidate.formula ||
    candidate.smiles ||
    candidate.name
  selectedKeys.value = [baseKey ? `${baseKey}-${Math.max(index, 0)}` : `row-${Math.max(index, 0)}`]
  message.info(`已选中候选材料：${candidate.name || candidate.formula || candidate.smiles}`)
}

async function onPredict() {
  loading.value = true
  predictError.value = ''
  try {
    let res
    if (materialType.value === 'crystal') {
      // 解析元素并诊断无效符号（如 NMC811 俗称 → M 非合法元素符号）
      const { elements, invalidSymbols } = parseElements(crystalForm.formula)
      if (invalidSymbols.length > 0) {
        loading.value = false
        candidates.value = []
        selected.value = []
        selectedKeys.value = []
        predictError.value = `输入的化学式无法解析为合法元素：包含无效符号「${invalidSymbols.join('、')}」。` +
          '请使用标准化学式（如 LiCoO2、LiNi0.8Mn0.1Co0.1O2），而不是俗称或缩写（如 NMC811）。'
        return
      }
      if (elements.length === 0) {
        loading.value = false
        candidates.value = []
        selected.value = []
        selectedKeys.value = []
        predictError.value = '输入的化学式无法解析出任何元素，请检查后重试。'
        return
      }
      // 多目标模式
      if (crystalForm.optimize_mode === 'multi' && crystalForm.multi_objective_props.length > 0) {
        const targetProperties = crystalForm.multi_objective_props.map((prop) => {
          const cfg = multiObjectiveConfig[prop] || { weight: 0.5, direction: 'maximize', min: null, max: null }
          return {
            property: prop,
            weight: cfg.weight,
            direction: cfg.direction,
            min: cfg.min,
            max: cfg.max,
          }
        })
        res = await discoverCrystal({
          elements,
          target_property: crystalForm.target_property,
          num_candidates: crystalForm.num_candidates,
          target_properties: targetProperties,
          scenario_id: currentScenarioId.value,
        })
      } else {
        res = await discoverCrystal({
          elements,
          target_property: crystalForm.target_property,
          num_candidates: crystalForm.num_candidates,
          scenario_id: currentScenarioId.value,
        })
      }
    } else {
      res = await discoverPolymer({
        smiles: polymerForm.smiles,
        num_candidates: polymerForm.num_candidates,
        scenario_id: currentScenarioId.value,
      })
    }
    let results = res.candidates || []
    // 去重：按 formula/smiles 去重，只保留第一条
    const seen = new Set()
    results = results.filter(r => {
      const key = r.formula || r.smiles
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    candidates.value = results
    selected.value = []
    selectedKeys.value = []
    if (candidates.value.length === 0) {
      // 结合后端诊断信息给出具体原因，避免笼统的"未生成候选材料"
      const blocks = res?.blocked_count || 0
      if (blocks > 0) {
        predictError.value = `生成了 ${blocks} 个候选，但均未通过化学式合法性 / 元素约束校验，未返回可用候选。` +
          '请调整元素组合或目标属性后点击「重试」再次尝试。'
      } else if (res?.degraded) {
        predictError.value = '候选数量不足，未返回可用候选材料。请调整参数（如放宽元素范围）后点击「重试」再次尝试。'
      } else {
        predictError.value = '未生成候选材料，请调整参数后点击「重试」再次尝试。'
      }
    } else {
      message.success(`预测完成，生成 ${candidates.value.length} 个候选材料`)
    }
  } catch (e) {
    // 透出具体错误原因，便于用户定位问题（超时/解析失败/服务异常等）
    candidates.value = []
    selected.value = []
    selectedKeys.value = []
    predictError.value = e?.response?.data?.error || e?.message || '预测执行失败，请点击「重试」再次尝试；若持续失败，请检查系统服务或稍后再试。'
  } finally {
    loading.value = false
  }
}

async function runCrossScale() {
  if (!crossScaleForm.formula && !crossScaleForm.smiles) {
    message.warning('请先输入化学式或 SMILES')
    return
  }
  if (!crossScaleForm.scales.length) {
    message.warning('请至少选择一个建模尺度')
    return
  }
  loading.value = true
  try {
    const res = await crossScalePredict({
      material_type: crossScaleForm.material_type,
      formula: crossScaleForm.formula,
      smiles: crossScaleForm.smiles,
      scales: crossScaleForm.scales,
      model_type: crossScaleForm.model_type || null,
    })
    // 防御性校验：确保 res 是对象，避免渲染时崩溃
    crossScaleResult.value = (res && typeof res === 'object') ? res : null
    // 切换到第一个有结果的标签页（兜底 molecular，若无则保持空）
    const validTabs = ['molecular', 'reaction', 'continuum', 'coupled'].filter(
      (k) => crossScaleResult.value?.[k]
    )
    if (validTabs.length) {
      crossScaleTab.value = validTabs[0]
    }
    if (crossScaleResult.value) {
      message.success('跨尺度建模完成')
    } else {
      message.warning('跨尺度建模返回数据为空，请稍后重试')
    }
  } catch {
    crossScaleResult.value = null
    /* 错误由拦截器统一处理 */
  } finally {
    loading.value = false
  }
}

// P2-1：开始预测/发送合成/发送实验均为无副作用操作，直接执行，不再弹二次确认；
// 仅"反哺到物料库"（会创建审批单）保留确认弹窗。
function withScenario(query) {
  return currentScenarioId.value ? { ...query, scenario_id: currentScenarioId.value } : query
}

function sendToSynthesis(candidateOverride = null) {
  const candidate = candidateOverride || selected.value[0]
  // 优先使用选中的候选，否则使用当前输入
  const smiles = candidate?.smiles || candidate?.formula || polymerForm.smiles || crystalForm.formula
  const formula = candidate?.formula || crystalForm.formula || polymerForm.smiles
  router.push({
    path: '/synthesis',
    query: withScenario({ smiles, formula }),
  })
  candidateOverride ? message.info(`已发送「${candidate?.name || formula}」到合成页面`) : message.info('已发送到合成页面')
}

function sendToExperiment(candidateOverride = null) {
  const candidate = candidateOverride || selected.value[0]
  const formula = candidate?.formula || crystalForm.formula || polymerForm.smiles
  router.push({ path: '/experiments', query: withScenario({ formula }) })
  candidateOverride ? message.info(`已发送「${candidate?.name || formula}」到实验页面`) : message.info('已发送到实验页面')
}

function sendToFormula(candidateOverride = null) {
  const candidate = candidateOverride || selected.value[0]
  const target = candidate?.smiles || candidate?.formula || polymerForm.smiles || crystalForm.formula
  router.push({ path: '/formula-design', query: withScenario({ target }) })
  message.info('已发送到配方页面')
}

async function checkAvailability() {
  if (selected.value.length === 0) return
  availabilityLoading.value = true
  availabilityVisible.value = true
  try {
    const payload = selected.value.map((c) => ({
      candidate_id: c.candidate_id || c.id || c.formula || c.smiles || '',
      formula: c.formula || '',
      smiles: c.smiles || '',
      name: c.name || '',
    }))
    const res = await checkMaterialsAvailability(payload, 1.0)
    availabilityResults.value = res.results || []
  } catch (e) {
    message.error('原料可得性检查失败，请稍后重试或联系管理员')
    availabilityResults.value = []
  } finally {
    availabilityLoading.value = false
  }
}

function statusColor(status) {
  return { in_stock: 'green', partial_in_stock: 'orange', no_match: 'red' }[status] || 'default'
}

function statusLabel(status) {
  return { in_stock: '全部在库', partial_in_stock: '部分在库', no_match: '需新采购' }[status] || status
}

// --- 反哺到物料库（G2.4）---

function onConfirmOk() {
  confirmVisible.value = false
  if (confirmCallback) confirmCallback()
}

function promptFeedbackToMaterialDB() {
  if (selected.value.length === 0) return
  const candidate = selected.value[0]
  const name = candidate.name || candidate.formula || candidate.smiles || '预测物料'
  confirmTitle.value = '反哺到物料库'
  confirmContent.value = `确认将预测候选材料「${name}」作为预测值提交到物料库？提交后将生成物料申请，审批通过后写入物料库并标注为"预测值"。`
  confirmCallback = feedbackToMaterialDB
  confirmVisible.value = true
}

async function feedbackToMaterialDB() {
  const candidate = selected.value[0]
  if (!candidate) return
  const targetProp = crystalForm.target_property
  const valueField = FIELD_MAP[targetProp] || targetProp
  const predictedValue = candidate[valueField] ?? candidate[targetProp]
  const materialData = {
    material_id: '',
    name: candidate.name || candidate.formula || candidate.smiles || '预测物料',
    smiles: candidate.smiles || '',
    category: materialType.value === 'polymer' ? 'BASE_POLYMER' : 'FILLER',
    inventory_kg: 0,
    cost_per_kg: 0,
    supplier: '',
    reach_compliant: true,
    is_toxic: false,
    data_source: 'predicted',
    prediction_meta: {
      model: materialType.value === 'crystal' ? 'crystal_predictor' : 'polymer_predictor',
      predicted_property: targetProp,
      predicted_value: predictedValue != null ? String(predictedValue) : '',
    },
    update_reason: '性质预测结果反哺物料库',
  }
  try {
    await createMaterialRequest({
      material_data: materialData,
      request_type: 'add',
      requester: localStorage.getItem('userId') || '',
    })
    message.success('已提交物料申请（预测值），等待审批后写入物料库')
  } catch {
    // 错误由拦截器处理
  }
}

// ── 材料设计模块重组：「创建为候选材料」转正 ──
const promoteVisible = ref(false)
const promoteLoading = ref(false)
const promoteTarget = ref(null)
const promoteTmpId = ref('')
const promoteProjects = ref([])
const promoteProjectId = ref(undefined)
const promoteTasks = ref([])
const promoteTaskId = ref(undefined)

const promoteProjectOptions = computed(() =>
  promoteProjects.value.map((p) => ({ label: p.name || '未命名项目', value: p.project_id }))
)
const promoteTaskOptions = computed(() =>
  promoteTasks.value.map((t) => ({ label: t.title || '未命名任务', value: t.task_id }))
)

async function loadPromoteProjects() {
  try {
    const data = await listProjects()
    promoteProjects.value = Array.isArray(data) ? data : []
  } catch {
    promoteProjects.value = []
  }
}

async function onPromoteProjectChange() {
  promoteTaskId.value = undefined
  promoteTasks.value = []
  const pid = promoteProjectId.value
  if (!pid) return
  try {
    const data = await listProjectTasks(pid)
    promoteTasks.value = Array.isArray(data) ? data : (data?.tasks || [])
  } catch {
    promoteTasks.value = []
  }
}

// 为临时候选生成唯一 temp_result_id，作为来源谱系标识（origin_temp_id），用于追溯该候选源自哪次临时预测
function generateTempResultId(candidate, idx) {
  return `temp-${Date.now()}-${idx}-${Math.floor(Math.random() * 1000)}`
}

function openPromoteModal(candidate, idx) {
  promoteTarget.value = candidate
  // 使用唯一 temp_result_id 作为 origin_temp_id，避免基于化学式/cardKey 导致同化学式误去重
  promoteTmpId.value = generateTempResultId(candidate, idx)
  // 每次打开弹窗时重置项目/任务选择，确保用户明确选择归属
  promoteProjectId.value = undefined
  promoteTaskId.value = undefined
  promoteTasks.value = []
  if (promoteProjects.value.length === 0) {
    loadPromoteProjects()
  }
  promoteVisible.value = true
}

async function doPromote() {
  if (!promoteTaskId.value) {
    message.warning('请选择所属任务')
    return
  }
  if (!promoteTarget.value) return
  promoteLoading.value = true
  try {
    const record = await promoteFromTemporary({
      candidate: promoteTarget.value,
      material_type: materialType.value,
      project_id: promoteProjectId.value || '',
      task_id: promoteTaskId.value,
      origin_temp_id: promoteTmpId.value,
    })
    message.success('已创建为候选材料')
    promoteVisible.value = false
    // 通知父组件（候选工作台）切换到候选 Tab 并定位到新候选详情
    emit('promoted', {
      candidate: record,
      project_id: promoteProjectId.value || '',
      task_id: promoteTaskId.value,
    })
  } catch (e) {
    message.error(e?.message || '创建候选材料失败，请稍后重试')
  } finally {
    promoteLoading.value = false
  }
}
</script>

<style scoped>
.temp-prediction {
  padding: 16px;
  overflow-y: auto;
  height: 100%;
  box-sizing: border-box;
}

.prediction-tip {
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

.carry-alert {
  border-radius: var(--radius-lg);
}

.mode-switch {
  margin-bottom: 16px;
}

/* ── 两列布局：左侧表单 + 右侧 Agent 面板 ── */
.prediction-layout {
  display: flex;
  gap: var(--space-md, 16px);
  align-items: flex-start;
}

.prediction-main {
  flex: 1;
  min-width: 0;
}

/* 右侧 Agent 面板：固定宽度 */
.predict-agent-panel {
  flex-shrink: 0;
  width: 300px;
}

.predict-agent-card {
  background: var(--realsee-surface, #fff);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: var(--radius-xl, 12px);
  box-shadow: var(--shadow-card, 0 1px 3px rgba(0,0,0,0.05));
  padding: var(--space-lg, 16px);
  display: flex;
  flex-direction: column;
  gap: var(--space-md, 12px);
}

.predict-panel-title {
  font-size: var(--font-size-sm, 12px);
  font-weight: var(--font-weight-bold, 700);
  color: var(--text-muted, #8c8c8c);
  letter-spacing: 0.5px;
  text-transform: uppercase;
  padding-bottom: var(--space-sm, 8px);
  border-bottom: 1px solid var(--border-light, #f0f0f0);
}

.agent-select-block {
  margin-bottom: 4px;
}

.predict-head {
  display: flex;
  gap: var(--space-md, 12px);
  align-items: center;
}

.predict-avatar {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md, 8px);
  background: var(--primary-bg, #e6f7ff);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  flex-shrink: 0;
  line-height: 1;
}

.predict-info {
  flex: 1;
  min-width: 0;
}

.predict-name {
  font-size: var(--font-size-md, 14px);
  font-weight: var(--font-weight-bold, 700);
  color: var(--text-primary, #1a1a2e);
  margin-bottom: 4px;
}

.predict-tags-row {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.predict-role-tag,
.predict-builtin-tag {
  margin: 0;
  font-size: 11px;
  line-height: 18px;
  padding: 0 6px;
  border: none;
}

.predict-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.predict-section-title {
  font-size: var(--font-size-xs, 11px);
  font-weight: var(--font-weight-semibold, 600);
  color: var(--text-muted, #8c8c8c);
  letter-spacing: 0.3px;
}

.predict-desc {
  font-size: var(--font-size-sm, 13px);
  color: var(--text-primary, #1a1a2e);
  line-height: 1.6;
}

.predict-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.predict-tag {
  margin: 0;
  font-size: 11px;
  line-height: 18px;
  padding: 0 6px;
}

.predict-desc-list :deep(.ant-descriptions-item-label) {
  font-size: var(--font-size-xs, 11px);
  color: var(--text-muted, #8c8c8c);
  width: 60px;
}

.predict-desc-list :deep(.ant-descriptions-item-content) {
  font-size: var(--font-size-sm, 13px);
  color: var(--text-primary, #1a1a2e);
}

/* Agent 执行按钮区块：与上方信息分隔，固定在面板底部 */
.predict-action-block {
  margin-top: var(--space-md, 12px);
  padding-top: var(--space-md, 12px);
  border-top: 1px solid var(--border-light, #f0f0f0);
  display: flex;
  flex-direction: column;
  gap: var(--space-xs, 4px);
}

/* DisabledButton 包装 span 改为 block 以支持 block 按钮宽度 */
.predict-action-block :deep(.disabled-btn-wrap) {
  display: block;
  width: 100%;
}

.predict-action-block :deep(.ant-btn) {
  width: 100%;
}

.predict-action-hint {
  font-size: var(--font-size-xs, 11px);
  color: var(--text-muted, #8c8c8c);
  line-height: 1.5;
  text-align: center;
}

@media (max-width: 1100px) {
  /* 中等屏幕：两列改单列垂直堆叠，Agent 面板移至下方 */
  .prediction-layout {
    flex-direction: column;
  }
  .predict-agent-panel {
    width: 100%;
  }
}

.kv-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 4px 0;
  font-size: 13px;
}

.kv-label {
  color: var(--text-muted);
}

.result-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  min-width: 0;
}

.result-header :deep(.ant-tag) {
  margin: 0;
  font-variant-numeric: tabular-nums;
}

/* 多目标优化配置折叠面板：默认收起，减少占用空间 */
.mo-collapse {
  margin: 4px 0 12px;
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: 8px;
}

.mo-collapse :deep(.ant-collapse-header) {
  padding: 6px 12px !important;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  align-items: center;
}

.mo-collapse :deep(.ant-collapse-content-box) {
  padding: 0 12px 8px !important;
}

.mo-collapse .multi-objective-editor {
  margin: 0;
  padding: 0;
  background: transparent;
  border: none;
}

.chart-tabs {
  margin-top: 8px;
}

.chart-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 8px;
}

/* ── 结果视图切换与候选卡片流 ── */
.result-view-switch {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.candidate-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.c-card {
  border: 1px solid var(--border, #e8e8e8);
  border-radius: var(--radius-lg, 10px);
  padding: 12px;
  background: var(--light-bg-card, #fff);
  transition: border-color var(--transition), box-shadow var(--transition);
}

.c-card.is-checked {
  border-color: var(--primary);
  box-shadow: 0 0 0 1px var(--primary) inset;
}

.c-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.c-card-title {
  flex: 1;
  min-width: 0;
}

.c-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.c-formula {
  font-size: 12px;
  color: var(--text-muted, #8c8c8c);
  font-variant-numeric: tabular-nums;
}

.c-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  padding: 8px 0;
  border-top: 1px solid var(--border-light, #f0f0f0);
  border-bottom: 1px solid var(--border-light, #f0f0f0);
  margin-bottom: 8px;
}

.c-metric {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  font-size: 12px;
}

.c-label {
  color: var(--text-muted, #8c8c8c);
}

.c-value {
  color: var(--text-primary, #1a1a2e);
  font-variant-numeric: tabular-nums;
}

.c-collapse :deep(.ant-collapse-header) {
  padding: 6px 0 !important;
  font-size: 12px;
  font-weight: 500;
}

.c-collapse :deep(.ant-descriptions-item-label) {
  font-size: 12px;
  color: var(--text-muted, #8c8c8c);
  width: 110px;
}

.c-collapse :deep(.ant-descriptions-item-content) {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.c-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.empty-card :deep(.ant-card-body) {
  padding: 56px 0;
}

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

.template-chip:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.input-hint {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-muted);
}

/* 多目标优化编辑器 */
.multi-objective-editor {
  margin: 4px 0 12px;
  padding: 12px 14px;
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: 8px;
}

.multi-objective-editor .mo-header,
.multi-objective-editor .mo-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1.2fr 1fr 1fr;
  align-items: center;
  gap: 8px;
}

.multi-objective-editor .mo-header {
  padding: 4px 0;
  border-bottom: 1px solid var(--border, #e8e8e8);
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #5a5a5a);
}

.multi-objective-editor .mo-row {
  padding: 6px 0;
  font-size: 13px;
  color: var(--text-primary, #1a1a2e);
}

.multi-objective-editor .mo-col-prop {
  font-weight: 500;
}

/* 原料可得性检查模态框 */
.availability-block {
  padding: 12px 0;
  border-bottom: 1px dashed var(--border, #e8e8e8);
}

.availability-block:last-child {
  border-bottom: none;
}

.availability-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}

.candidate-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  word-break: break-all;
}

.cost-summary {
  margin-left: auto;
  font-size: 13px;
  color: var(--text-secondary, #595959);
  font-variant-numeric: tabular-nums;
}

.shortage {
  color: #1d4ed8;
  font-weight: 500;
}

/* ── 创建为候选材料转正弹窗 ── */
.promote-desc {
  font-size: 13px;
  color: var(--text-secondary, #595959);
  line-height: 1.6;
  margin-bottom: 16px;
}

.promote-target {
  margin-top: 12px;
  padding: 8px 12px;
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border-light, #f0f0f0);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary, #1a1a2e);
}
</style>