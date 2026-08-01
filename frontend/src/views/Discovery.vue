<template>
  <div class="discovery">
    <div class="page-header">
      <h1 class="page-title">材料发现</h1>
      <p class="page-subtitle">生成晶体或聚合物候选材料，按目标性质排序筛选</p>
    </div>

    <!-- P3-2：研发工作台派生上下文横幅 -->
    <ResearchContextBanner />

    <!-- Input Panel -->
    <a-card class="input-card" :bordered="false">
      <a-tabs v-model:activeKey="materialType">
        <a-tab-pane key="crystal">
          <template #tab>
            <ExperimentOutlined /> 晶体材料
          </template>
          <a-form class="discovery-form">
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="目标 / 化学式">
                  <a-input v-model:value="crystalForm.target" name="target" autocomplete="off" placeholder="例如 LiCoO2…" allow-clear />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="优化模式">
                  <a-radio-group v-model:value="crystalForm.optimize_mode">
                    <a-radio-button value="single">单目标</a-radio-button>
                    <a-radio-button value="multi">多目标优化</a-radio-button>
                  </a-radio-group>
                </a-form-item>
              </a-col>
            </a-row>

            <!-- 单目标模式 -->
            <a-form-item v-if="crystalForm.optimize_mode === 'single'" label="目标属性">
              <a-select v-model:value="crystalForm.target_property" :options="crystalPropertyOptions" />
            </a-form-item>

            <!-- 多目标优化模式 -->
            <div v-else>
              <a-form-item label="目标属性集">
                <a-select
                  v-model:value="crystalForm.multi_objective_props"
                  mode="multiple"
                  placeholder="选择多个目标属性…"
                  :options="multiObjectiveOptions"
                  style="width: 100%"
                />
                <span class="input-hint">支持多目标帕累托加权优化，可设置权重与约束条件</span>
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

            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="候选数量">
                  <a-input-number v-model:value="crystalForm.num_candidates" :min="1" :max="50" style="width: 100%" />
                  <span class="input-hint">范围 1~50，默认 10</span>
                </a-form-item>
              </a-col>
            </a-row>
            <a-form-item label="元素筛选">
              <a-select
                v-model:value="crystalForm.elements"
                mode="multiple"
                placeholder="选择元素（留空表示全部）…"
                :options="elementOptions"
                style="width: 100%"
              />
              <div class="template-chips">
                <span class="chip-label">体系模板：</span>
                <a-tag
                  v-for="tpl in elementTemplates"
                  :key="tpl.name"
                  class="template-chip"
                  role="button"
                  tabindex="0"
                  @click="crystalForm.elements = [...tpl.elements]"
                  @keydown.enter.prevent="crystalForm.elements = [...tpl.elements]"
                >
                  {{ tpl.name }}
                </a-tag>
              </div>
            </a-form-item>
            <a-form-item class="form-actions">
              <a-button type="primary" :loading="discoveryStore.loading" @click="onCrystalSubmit">
                <SearchOutlined /> 生成候选材料
              </a-button>
            </a-form-item>
          </a-form>
        </a-tab-pane>

        <a-tab-pane key="polymer">
          <template #tab>
            <ExperimentOutlined /> 聚合物电解质
          </template>
          <a-form class="discovery-form">
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="目标聚合物">
                  <a-input v-model:value="polymerForm.target" name="target" autocomplete="off" placeholder="例如 PEO…" allow-clear />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="优化模式">
                  <a-radio-group v-model:value="polymerForm.optimize_mode">
                    <a-radio-button value="single">单目标</a-radio-button>
                    <a-radio-button value="multi">多目标优化</a-radio-button>
                  </a-radio-group>
                </a-form-item>
              </a-col>
            </a-row>

            <!-- 多目标优化模式 -->
            <div v-if="polymerForm.optimize_mode === 'multi'">
              <a-form-item label="目标属性集">
                <a-select
                  v-model:value="polymerForm.multi_objective_props"
                  mode="multiple"
                  placeholder="选择多个目标属性…"
                  :options="polymerMultiObjectiveOptions"
                  style="width: 100%"
                />
                <span class="input-hint">聚合物支持多目标加权优化（电导率/分子量）</span>
              </a-form-item>

              <a-collapse
                v-if="polymerForm.multi_objective_props.length > 0"
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
                    <div v-for="prop in polymerForm.multi_objective_props" :key="prop" class="mo-row">
                      <span class="mo-col-prop">{{ polymerMultiObjectiveLabel(prop) }}</span>
                      <span class="mo-col-weight">
                        <a-input-number v-model:value="polymerMultiObjectiveConfig[prop].weight" :min="0" :max="1" :step="0.1" size="small" style="width: 80px" />
                      </span>
                      <span class="mo-col-dir">
                        <a-select v-model:value="polymerMultiObjectiveConfig[prop].direction" size="small" style="width: 100px">
                          <a-select-option value="maximize">最大化</a-select-option>
                          <a-select-option value="minimize">最小化</a-select-option>
                        </a-select>
                      </span>
                      <span class="mo-col-min">
                        <a-input-number v-model:value="polymerMultiObjectiveConfig[prop].min" size="small" style="width: 100px" placeholder="无" />
                      </span>
                      <span class="mo-col-max">
                        <a-input-number v-model:value="polymerMultiObjectiveConfig[prop].max" size="small" style="width: 100px" placeholder="无" />
                      </span>
                    </div>
                  </div>
                </a-collapse-panel>
              </a-collapse>
            </div>

            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="候选数量">
                  <a-input-number v-model:value="polymerForm.num_candidates" :min="1" :max="50" style="width: 100%" />
                </a-form-item>
              </a-col>
            </a-row>
            <a-form-item class="form-actions">
              <a-button type="primary" :loading="discoveryStore.loading" @click="onPolymerSubmit">
                <SearchOutlined /> 生成候选材料
              </a-button>
            </a-form-item>
          </a-form>
        </a-tab-pane>

        <a-tab-pane key="generate">
          <template #tab>
            <RocketOutlined /> 生成模式
          </template>
          <a-form class="discovery-form">
            <a-form-item label="生成类型">
              <a-radio-group v-model:value="genForm.mode">
                <a-radio-button value="molecule">分子生成</a-radio-button>
                <a-radio-button value="crystal">晶体生成</a-radio-button>
              </a-radio-group>
            </a-form-item>

            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item v-if="genForm.mode === 'molecule'" label="目标属性">
                  <a-input v-model:value="genForm.target_property" name="target_property" autocomplete="off" placeholder="例如 离子电导率…" allow-clear />
                </a-form-item>
                <a-form-item v-else label="空间群">
                  <a-input v-model:value="genForm.space_groups" name="space_groups" autocomplete="off" placeholder="例如 R-3m, Fm-3m…" allow-clear />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="最大原子数">
                  <a-input-number v-model:value="genForm.max_atoms" :min="1" :max="200" style="width: 100%" />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item label="元素选择">
              <a-select
                v-model:value="genForm.elements"
                mode="multiple"
                placeholder="选择元素（留空表示全部）…"
                :options="elementOptions"
                style="width: 100%"
              />
            </a-form-item>

            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="生成数量">
                  <a-input-number v-model:value="genForm.count" :min="1" :max="50" style="width: 100%" />
                  <span class="input-hint">范围 1~50，默认 10</span>
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item class="form-actions">
              <a-button type="primary" :loading="discoveryStore.loading" @click="onGenerateSubmit">
                <RocketOutlined /> 开始生成
              </a-button>
            </a-form-item>
          </a-form>
        </a-tab-pane>

        <a-tab-pane key="verify">
          <template #tab>
            <ThunderboltOutlined /> 并行验证
          </template>

          <!-- 工具栏 -->
          <div class="verify-toolbar">
            <a-button type="primary" @click="showCreateIdeaModal">
              <PlusOutlined /> 创建 IDEA
            </a-button>
            <a-button
              type="primary"
              ghost
              :loading="verifying"
              :disabled="selectedIdeaIds.length === 0"
              @click="onParallelVerify"
            >
              <ThunderboltOutlined /> 启动并行验证 ({{ selectedIdeaIds.length }})
            </a-button>
            <a-button @click="loadIdeas">刷新</a-button>
            <span class="input-hint" style="margin-left: 8px">选择 3-5 个 IDEA 并行验证，对比关键指标</span>
          </div>

          <!-- IDEA 列表 -->
          <a-table
            :columns="ideaColumns"
            :data-source="ideas"
            :row-key="(r) => r.idea_id"
            :row-selection="{ selectedRowKeys: selectedIdeaIds, onChange: onSelectIdeas }"
            size="small"
            :pagination="false"
            :loading="ideasLoading"
            class="idea-table"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'identifier'">
                <span style="font-size: 12px; color: var(--text-secondary, #595959)">
                  {{ record.smiles || record.formula || '—' }}
                </span>
              </template>
              <template v-if="column.key === 'material_type'">
                <a-tag :color="record.material_type === 'crystal' ? 'blue' : 'purple'">
                  {{ record.material_type === 'crystal' ? '晶体' : '分子/聚合物' }}
                </a-tag>
              </template>
              <template v-if="column.key === 'status'">
                <a-tag :color="ideaStatusColor(record.status)">{{ ideaStatusLabel(record.status) }}</a-tag>
              </template>
              <template v-if="column.key === 'score'">
                <span style="font-variant-numeric: tabular-nums">{{ (record.score * 100).toFixed(0) }}%</span>
              </template>
              <template v-if="column.key === 'actions'">
                <a-tooltip :title="record.status === 'preferred' ? '该创意已是优选状态' : ''">
                  <span class="tt-btn-wrap">
                    <a-button
                      size="small"
                      type="link"
                      :disabled="record.status === 'preferred'"
                      @click="markIdeaStatus(record.idea_id, 'preferred')"
                    >优选</a-button>
                  </span>
                </a-tooltip>
                <a-tooltip :title="record.status === 'eliminated' ? '该创意已淘汰' : ''">
                  <span class="tt-btn-wrap">
                    <a-button
                      size="small"
                      type="link"
                      danger
                      :disabled="record.status === 'eliminated'"
                      @click="markIdeaStatus(record.idea_id, 'eliminated')"
                    >淘汰</a-button>
                  </span>
                </a-tooltip>
              </template>
            </template>
          </a-table>

          <!-- 任务看板：验证进度 -->
          <div v-if="verifyTaskIds.length > 0" class="verify-board">
            <div class="board-title">
              <ThunderboltOutlined /> 验证进度看板
              <a-tag v-if="verifying" color="processing">进行中</a-tag>
              <a-tag v-else color="success">已完成</a-tag>
            </div>
            <a-row :gutter="[16, 16]">
              <a-col v-for="id in verifyTaskIds" :key="id" :span="8">
                <div class="verify-task-item">
                  <div class="task-header">
                    <span class="task-name">{{ getIdeaName(id) }}</span>
                    <a-tag v-if="!verifying" :color="getVerifyResultColor(id)">
                      {{ getVerifyResultStatus(id) }}
                    </a-tag>
                  </div>
                  <a-progress
                    :percent="getVerifyProgress(id)"
                    :status="getVerifyProgressStatus(id)"
                  />
                </div>
              </a-col>
            </a-row>
          </div>

          <!-- 卡片矩阵：验证结果对比 -->
          <div v-if="verifyResults.length > 0" class="verify-results">
            <div class="board-title">
              <BarChartOutlined /> 验证结果对比
            </div>
            <a-row :gutter="[16, 16]">
              <a-col v-for="res in verifyResults" :key="res.idea_id" :xs="24" :sm="12" :md="8" :lg="6">
                <a-card size="small" class="result-card-item" :bordered="true">
                  <template #title>
                    <div class="result-card-header">
                      <span class="result-name">{{ getIdeaName(res.idea_id) }}</span>
                      <a-tag :color="ideaStatusColor(res.status)">{{ ideaStatusLabel(res.status) }}</a-tag>
                    </div>
                  </template>
                  <div class="result-score">
                    <span class="score-label">综合评分</span>
                    <a-progress
                      type="circle"
                      :percent="Math.round((res.score || 0) * 100)"
                      :width="60"
                      :stroke-color="res.score >= 0.5 ? '#52c41a' : '#fa8c16'"
                    />
                  </div>
                  <a-divider style="margin: 8px 0" />
                  <div
                    v-for="(pred, propName) in res.result?.predictions || {}"
                    :key="propName"
                    class="prop-row"
                  >
                    <div class="prop-header">
                      <span class="prop-name">{{ propName }}</span>
                      <a-tag v-if="pred.met" color="success" :bordered="false">达标</a-tag>
                      <a-tag v-else color="error" :bordered="false">未达标</a-tag>
                    </div>
                    <div class="prop-values">
                      <span class="prop-value">
                        预测: <template v-if="pred.error">—</template><ScientificNotation v-else :value="pred.value" :precision="4" /><small v-if="pred.unit"> {{ pred.unit }}</small>
                      </span>
                      <span class="prop-target" v-if="pred.target_value != null && pred.target_value !== ''">
                        目标: {{ pred.target_value }}
                      </span>
                    </div>
                  </div>
                  <a-divider style="margin: 8px 0" />
                  <div class="result-actions">
                    <a-tooltip :title="getIdeaStatus(res.idea_id) === 'preferred' ? '该创意已是优选状态' : ''">
                      <span class="tt-btn-wrap">
                        <a-button
                          size="small"
                          :disabled="getIdeaStatus(res.idea_id) === 'preferred'"
                          @click="markIdeaStatus(res.idea_id, 'preferred')"
                        >优选</a-button>
                      </span>
                    </a-tooltip>
                    <a-tooltip :title="getIdeaStatus(res.idea_id) === 'eliminated' ? '该创意已淘汰' : ''">
                      <span class="tt-btn-wrap">
                        <a-button
                          size="small"
                          danger
                          :disabled="getIdeaStatus(res.idea_id) === 'eliminated'"
                          @click="markIdeaStatus(res.idea_id, 'eliminated')"
                        >淘汰</a-button>
                      </span>
                    </a-tooltip>
                  </div>
                </a-card>
              </a-col>
            </a-row>
          </div>
        </a-tab-pane>
      </a-tabs>
    </a-card>

    <!-- Results -->
    <a-card class="result-card" :bordered="false" v-if="hasResults && materialType !== 'verify' && materialType !== 'generate'">
      <template #title>
        <div class="result-header">
          <span>候选结果</span>
          <a-tag color="blue">{{ resultCount }} 个候选材料</a-tag>
          <a-alert
            v-if="selectedCandidates.length === 0"
            type="info"
            show-icon
            :message="'请勾选候选材料后，再使用下游操作按钮'"
            class="selection-hint"
          />
          <a-space wrap>
            <a-tooltip title="将候选材料发送到性质预测模块，进一步预测电导率、带隙等关键属性">
              <a-button size="small" @click="sendToPrediction">发送到预测</a-button>
            </a-tooltip>
            <a-tooltip title="将候选材料发送到合成路径模块，规划可行的合成路线">
              <a-button size="small" @click="sendToSynthesis">发送到合成</a-button>
            </a-tooltip>
            <a-tooltip title="将候选材料发送到实验工作台，创建实验任务进行实测">
              <a-button size="small" @click="sendToExperiment">发送到实验</a-button>
            </a-tooltip>
            <a-tooltip title="将候选材料发送到配方与工艺模块，设计电解液配方">
              <a-button size="small" @click="sendToFormula">发送到配方</a-button>
            </a-tooltip>
            <a-tooltip title="基于候选材料创建样品记录，纳入样品管理流程">
              <a-button size="small" @click="sendToSample">创建样品</a-button>
            </a-tooltip>
            <a-tooltip title="检查候选材料所需原料在库存中的可得性，辅助采购决策">
              <a-button size="small" type="primary" ghost :loading="availabilityLoading" @click="checkAvailability">检查原料可得性</a-button>
            </a-tooltip>
          </a-space>
        </div>
      </template>
      <a-alert v-if="!hasMultiObjective && currentData.length > 0"
        type="info" show-icon
        message="开启多目标优化模式后可查看帕累托前沿分析图"
        style="margin-bottom: 12px"
      />
      <a-tabs v-if="hasMultiObjective" size="small" class="chart-tabs">
        <a-tab-pane key="pareto" tab="帕累托前沿">
          <ParetoChart :candidates="candidatesWithObjectives" @select="onChartSelect" />
        </a-tab-pane>
        <a-tab-pane key="radar" tab="雷达图">
          <RadarChart :candidates="candidatesWithObjectives" />
        </a-tab-pane>
      </a-tabs>
      <CandidateTable :data="currentData" :loading="discoveryStore.loading" :type="materialType" :selectable="true" :selected="selectedCandidateKeys" :moObjectives="moObjectivesForTable" @select="onSelectCandidates" />
    </a-card>

    <!-- 生成模式结果 -->
    <a-card class="result-card" :bordered="false" v-else-if="hasGeneratedResults">
      <template #title>
        <div class="result-header">
          <span>生成结果</span>
          <a-tag color="blue">{{ discoveryStore.generatedCandidates.length }} 个候选材料</a-tag>
          <span class="confidence-legend">置信度 <span class="legend-green">≥ 0.9</span> · <span class="legend-orange">&lt; 0.7</span></span>
        </div>
      </template>
      <a-table
        :columns="generatedColumns"
        :data-source="generatedTableData"
        :loading="discoveryStore.loading"
        size="small"
        :pagination="{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }"
        :row-key="(r) => r._rowKey"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'structure'">
            <StructureView
              :smiles="genForm.mode === 'molecule' ? (record.smiles || '') : ''"
              :formula="record.formula || ''"
              :space-group="record.space_group || ''"
              :structure-type="record.structure_type || ''"
              :kind="genForm.mode === 'molecule' ? 'molecule' : 'crystal'"
              :size="120"
            />
          </template>
          <template v-else-if="column.key === 'formula'">
            <ChemicalFormula :formula="record.formula || ''" size="small" />
          </template>
          <template v-else-if="column.key === 'confidence'">
            <div class="confidence-cell">
              <a-progress
                :percent="Math.round(record.confidence * 100)"
                :stroke-color="confidenceColor(record.confidence)"
                size="small"
                :show-info="false"
              />
              <span :style="{ color: confidenceColor(record.confidence) }" class="confidence-value">
                {{ record.confidence.toFixed(2) }}
              </span>
            </div>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Empty State -->
    <a-card class="empty-card" :bordered="false" v-else-if="materialType !== 'verify'">
      <EmptyState type="data" description="选择参数并点击「生成候选材料」开始材料发现" />
    </a-card>

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

    <!-- 创建 IDEA 抽屉 -->
    <a-drawer
      :open="createIdeaVisible"
      title="创建假设 (IDEA)"
      placement="right"
      width="640px"
      @update:open="(v) => (createIdeaVisible = v)"
    >
      <a-form :label-col="{ span: 6 }" :wrapper-col="{ span: 16 }">
        <a-form-item label="名称">
          <a-input v-model:value="createForm.name" placeholder="如 PEO-LiTFSI 电解质" />
        </a-form-item>
        <a-form-item label="材料类型">
          <a-radio-group v-model:value="createForm.material_type">
            <a-radio-button value="molecule">分子/聚合物</a-radio-button>
            <a-radio-button value="crystal">晶体</a-radio-button>
          </a-radio-group>
        </a-form-item>
        <a-form-item v-if="createForm.material_type === 'molecule'" label="SMILES">
          <a-input v-model:value="createForm.smiles" placeholder="如 CCO" />
        </a-form-item>
        <a-form-item label="化学式">
          <a-input v-model:value="createForm.formula" placeholder="如 LiCoO2" />
        </a-form-item>
        <a-form-item label="目标属性">
          <div v-for="(tp, idx) in createForm.target_properties" :key="idx" class="target-prop-row">
            <a-select
              v-model:value="tp.name"
              placeholder="选择属性"
              style="width: 40%"
              :options="ideaPropertyOptions"
              show-search
              allow-clear
            />
            <a-select v-model:value="tp.direction" style="width: 25%">
              <a-select-option value="maximize">最大化</a-select-option>
              <a-select-option value="minimize">最小化</a-select-option>
            </a-select>
            <a-input-number v-model:value="tp.target_value" placeholder="目标值" style="width: 25%" />
            <a-button size="small" type="link" danger @click="createForm.target_properties.splice(idx, 1)">
              <DeleteOutlined />
            </a-button>
          </div>
          <a-button size="small" type="dashed" @click="addTargetProp">
            <PlusOutlined /> 添加目标属性
          </a-button>
        </a-form-item>
        <a-form-item label="备注">
          <a-textarea v-model:value="createForm.notes" :rows="2" />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="creating" @click="createIdeaVisible = false">取消</a-button>
          <a-button type="primary" :loading="creating" @click="onCreateIdea">保存</a-button>
        </a-space>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useMdmDict, useUnitSymbols } from '@/utils/mdmDict'
import { industrialCategoryLabel } from '@/constants/materialTypes'
import { useRoute, useRouter } from 'vue-router'
import {
  ExperimentOutlined,
  SearchOutlined,
  ThunderboltOutlined,
  PlusOutlined,
  DeleteOutlined,
  BarChartOutlined,
  RocketOutlined,
} from '@ant-design/icons-vue'
import { useDiscoveryStore } from '@/stores/discovery'
import { getOptions } from '@/api/properties'
import { checkMaterialsAvailability } from '@/api/rawMaterials'
import { listIdeas, createIdea, updateIdeaStatus, parallelVerifyIdeas } from '@/api/ideas'
import CandidateTable from '@/components/CandidateTable.vue'
import StructureView from '@/components/StructureView.vue'
import ParetoChart from '@/components/ParetoChart.vue'
import RadarChart from '@/components/RadarChart.vue'
import ResearchContextBanner from '@/components/ResearchContextBanner.vue'
import EmptyState from '@/components/EmptyState.vue'

const discoveryStore = useDiscoveryStore()
const route = useRoute()
const router = useRouter()
const selectedCandidates = ref([])
const selectedCandidateKeys = ref([])
const materialType = ref('crystal')
const currentScenarioId = ref('')

const crystalForm = reactive({
  target: '',
  target_property: 'ionic_conductivity',
  optimize_mode: 'single', // 'single' | 'multi'
  multi_objective_props: [], // 多目标模式下选中的属性 key 列表
  num_candidates: 10,
  elements: [],
})

const polymerForm = reactive({
  target: '',
  num_candidates: 10,
  optimize_mode: 'single', // 'single' | 'multi'
  multi_objective_props: [], // 多目标模式下选中的属性 key 列表
})

const genForm = reactive({
  mode: 'molecule', // 'molecule' | 'crystal'
  elements: [],
  target_property: '',
  space_groups: '',
  max_atoms: 30,
  count: 10,
})

const crystalPropertyOptions = ref([])
const optionsCtrl = new AbortController()

// 多目标优化可选项（与后端 _PROPERTY_GETTERS 对齐），优先从 MDM 主数据加载
const multiObjectiveOptions = ref([
  { label: '离子电导率', value: 'ionic_conductivity' },
  { label: '带隙', value: 'band_gap' },
  { label: '形成能', value: 'formation_energy' },
  { label: '稳定性', value: 'stability' },
  { label: '能量高于凸包', value: 'energy_above_hull' },
])

// 多目标配置：每个属性对应 { weight, direction, min, max }
const multiObjectiveConfig = reactive({
  ionic_conductivity: { weight: 0.5, direction: 'maximize', min: null, max: null },
  band_gap: { weight: 0.3, direction: 'maximize', min: null, max: null },
  formation_energy: { weight: 0.3, direction: 'minimize', min: null, max: null },
  stability: { weight: 0.3, direction: 'maximize', min: null, max: null },
  energy_above_hull: { weight: 0.2, direction: 'minimize', min: null, max: null },
})

function multiObjectiveLabel(key) {
  const opt = multiObjectiveOptions.value.find((o) => o.value === key)
  return opt ? opt.label : key
}

// 聚合物多目标可选项（与后端 _POLY_PROPERTY_GETTERS 对齐），优先从 MDM 主数据加载
const polymerMultiObjectiveOptions = ref([
  { label: '离子电导率', value: 'ionic_conductivity' },
  { label: '分子量', value: 'molecular_weight' },
])

const polymerMultiObjectiveConfig = reactive({
  ionic_conductivity: { weight: 0.7, direction: 'maximize', min: null, max: null },
  molecular_weight: { weight: 0.3, direction: 'minimize', min: null, max: null },
})

function polymerMultiObjectiveLabel(key) {
  const opt = polymerMultiObjectiveOptions.value.find((o) => o.value === key)
  return opt ? opt.label : key
}

const LAST_CRYSTAL_TARGET_KEY = 'battery_discovery:last_crystal_target'
const LAST_POLYMER_TARGET_KEY = 'battery_discovery:last_polymer_target'
const LAST_FORMULA_KEY = 'battery_discovery:last_formula'

const elementOptions = ['Li', 'Co', 'Fe', 'Mn', 'Ni', 'O', 'P', 'S', 'Ti', 'Zr', 'La', 'Na', 'Al', 'Si', 'F', 'Cl'].map((e) => ({ label: e, value: e }))

// 常见电池材料体系模板，便于快速切换研发方向
const elementTemplates = [
  { name: '锂离子正极', elements: ['Li', 'Co', 'Ni', 'Mn', 'O'] },
  { name: '磷酸铁锂', elements: ['Li', 'Fe', 'P', 'O'] },
  { name: '钠离子电池', elements: ['Na', 'Fe', 'Mn', 'O', 'P'] },
  { name: '硫化物固态电解质', elements: ['Li', 'P', 'S'] },
  { name: '氧化物固态电解质', elements: ['La', 'Zr', 'O'] },
  { name: '钛酸锂负极', elements: ['Li', 'Ti', 'O'] },
]

function parseFormula(formula) {
  if (!formula) return []
  const matches = String(formula).match(/[A-Z][a-z]?/g) || []
  return [...new Set(matches)].filter((el) => elementOptions.some((o) => o.value === el))
}

function applyQueryParams() {
  const { formula, target, material_scope, target_property, goal, scenario_id } = route.query
  if (formula) {
    materialType.value = 'crystal'
    const f = String(formula)
    crystalForm.target = f
    crystalForm.elements = parseFormula(f)
  } else if (target) {
    materialType.value = 'polymer'
    polymerForm.target = String(target)
  } else if (goal) {
    // P0-001：工作台派生上下文无具体化学式时，用 goal 文本预填目标
    const g = String(goal)
    if (material_scope === 'polymer' || material_scope === 'electrolyte') {
      materialType.value = 'polymer'
      polymerForm.target = g
    } else {
      materialType.value = 'crystal'
      crystalForm.target = g
    }
  } else if (material_scope === 'polymer' || material_scope === 'electrolyte') {
    // P3-2：研发工作台派生上下文 —— 材料范围映射到对应页签
    materialType.value = 'polymer'
  } else if (material_scope === 'crystal') {
    materialType.value = 'crystal'
  }
  // P3-2/P0-001：目标属性预填（单目标模式），避免重复录入约束参数
  if (target_property) {
    crystalForm.optimize_mode = 'single'
    crystalForm.target_property = String(target_property)
  }
  // P0-001：保存场景 ID 供下游传递
  if (scenario_id) {
    currentScenarioId.value = String(scenario_id)
  }
}

// 从 MDM 加载选项，失败或结果为空时使用本地兜底
async function loadMdmOptions(loader, optionsRef, fallbackList) {
  try {
    const loaded = await loader()
    if (loaded && loaded.length > 0) {
      optionsRef.value = loaded
      return true
    }
  } catch (e) {
    console.warn('加载 MDM 选项失败:', e)
  }
  optionsRef.value = fallbackList
  return false
}

// 从 MDM 加载属性选项，仅保留与本地 value 兼容的项，避免 value 类型不一致导致接口异常
async function loadMdmPropertyOptions(loader, optionsRef, fallbackList) {
  try {
    const loaded = await loader()
    const fallbackValues = new Set(fallbackList.map((o) => o.value))
    const matched = (loaded || []).filter((o) => fallbackValues.has(o.value))
    if (matched.length > 0) {
      optionsRef.value = matched
      return true
    }
  } catch (e) {
    console.warn('加载 MDM 属性选项失败:', e)
  }
  optionsRef.value = fallbackList
  return false
}

onMounted(async () => {
  applyQueryParams()

  // URL 无参数时从 sessionStorage 兜底恢复（P3-2 派生上下文优先，跳过恢复避免覆盖材料范围）
  if (!route.query.formula && !route.query.target && !route.query.material_scope) {
    const savedCrystal = sessionStorage.getItem(LAST_CRYSTAL_TARGET_KEY)
    const savedPolymer = sessionStorage.getItem(LAST_POLYMER_TARGET_KEY)
    if (materialType.value === 'polymer' && savedPolymer) {
      polymerForm.target = savedPolymer
    } else if (savedCrystal) {
      materialType.value = 'crystal'
      crystalForm.target = savedCrystal
      crystalForm.elements = parseFormula(savedCrystal)
    }
  }

  try {
    const res = await getOptions({ usable_in: 'predictable' }, { signal: optionsCtrl.signal })
    crystalPropertyOptions.value = res.options
  } catch (e) {
    if (e.name === 'AbortError' || e.code === 'ERR_CANCELED' || e.message === 'canceled') return
    crystalPropertyOptions.value = [
      { label: '离子电导率', value: 'ionic_conductivity' },
      { label: '带隙', value: 'band_gap' },
      { label: '形成能', value: 'formation_energy' },
    ]
  }

  // 从 MDM 主数据加载下拉选项
  const { statusOptions, propertyOptions } = useMdmDict()
  loadUnitSymbols()
  const results = await Promise.all([
    loadMdmOptions(() => statusOptions('idea'), ideaStatusOptions, ideaStatusOptions.value),
    loadMdmPropertyOptions(propertyOptions, ideaPropertyOptions, ideaPropertyOptions.value),
    loadMdmPropertyOptions(propertyOptions, multiObjectiveOptions, multiObjectiveOptions.value),
    loadMdmPropertyOptions(propertyOptions, polymerMultiObjectiveOptions, polymerMultiObjectiveOptions.value),
  ])
  if (results.some((ok) => !ok)) {
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
})

onBeforeUnmount(() => {
  optionsCtrl.abort()
})

const hasResults = computed(() => {
  if (materialType.value === 'verify' || materialType.value === 'generate') return false
  return materialType.value === 'crystal'
    ? discoveryStore.crystalCandidates.length > 0
    : discoveryStore.polymerCandidates.length > 0
})

const hasGeneratedResults = computed(() =>
  materialType.value === 'generate' && discoveryStore.generatedCandidates.length > 0
)

const currentData = computed(() => {
  return materialType.value === 'crystal'
    ? discoveryStore.crystalCandidates
    : discoveryStore.polymerCandidates
})

const resultCount = computed(() => currentData.value.length)

// 属性 key → 候选字段映射
const CRYSTAL_FIELD_MAP = {
  ionic_conductivity: 'ionic_conductivity_estimate',
  band_gap: 'band_gap',
  formation_energy: 'formation_energy',
  stability: 'stability_score',
  energy_above_hull: 'energy_above_hull',
}
const POLYMER_FIELD_MAP = {
  ionic_conductivity: 'predicted_ionic_conductivity',
  molecular_weight: 'molecular_weight',
}

const activeMultiObjectiveProps = computed(() => {
  if (materialType.value === 'crystal') return crystalForm.multi_objective_props
  return polymerForm.multi_objective_props
})

const activeMultiObjectiveConfig = computed(() => {
  if (materialType.value === 'crystal') return multiObjectiveConfig
  return polymerMultiObjectiveConfig
})

const activeMultiObjectiveOptions = computed(() => {
  if (materialType.value === 'crystal') return multiObjectiveOptions.value
  return polymerMultiObjectiveOptions.value
})

const activeFieldMap = computed(() => {
  if (materialType.value === 'crystal') return CRYSTAL_FIELD_MAP
  return POLYMER_FIELD_MAP
})

const hasMultiObjective = computed(() => {
  return activeMultiObjectiveProps.value.length > 0 && currentData.value.length > 0
})

const candidatesWithObjectives = computed(() => {
  if (!hasMultiObjective.value) return []
  const props_keys = activeMultiObjectiveProps.value
  const config = activeMultiObjectiveConfig.value
  const options = activeMultiObjectiveOptions.value
  const fieldMap = activeFieldMap.value

  return currentData.value.map((c) => {
    const objectives = props_keys.map((key) => {
      const fieldName = fieldMap[key] || key
      const opt = options.find((o) => o.value === key)
      const cfg = config[key] || { weight: 0.5, direction: 'maximize', min: null, max: null }
      const name = opt ? opt.label : key
      return {
        name,
        key,
        value: c[fieldName] ?? c[key] ?? null,
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
  const fieldMap = activeFieldMap.value
  const config = activeMultiObjectiveConfig.value
  const options = activeMultiObjectiveOptions.value
  return activeMultiObjectiveProps.value.map((key) => {
    const opt = options.find((o) => o.value === key)
    const cfg = config[key] || {}
    return {
      key: fieldMap[key] || key,
      name: opt ? opt.label : key,
      min: cfg.min,
      max: cfg.max,
    }
  })
})

function onSelectCandidates(rows, keys) {
  selectedCandidates.value = rows
  selectedCandidateKeys.value = keys || []
}

function onChartSelect(candidate) {
  selectedCandidates.value = [candidate]
  const index = currentData.value.findIndex((c) =>
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
  selectedCandidateKeys.value = [baseKey ? `${baseKey}-${Math.max(index, 0)}` : `row-${Math.max(index, 0)}`]
  message.info(`已选中候选材料：${candidate.name || candidate.formula || candidate.smiles}`)
}

function saveLastFormula(formula) {
  if (formula) sessionStorage.setItem(LAST_FORMULA_KEY, formula)
}

function withScenario(query) {
  return currentScenarioId.value ? { ...query, scenario_id: currentScenarioId.value } : query
}

function requireSelected() {
  if (selectedCandidates.value.length === 0) {
    message.warning('请先在表格中勾选候选材料，再执行下游操作')
    return false
  }
  return true
}

function sendToPrediction() {
  if (!requireSelected()) return
  const candidate = selectedCandidates.value[0]
  saveLastFormula(candidate.formula)
  router.push({ path: '/prediction', query: withScenario({ formula: candidate.formula, smiles: candidate.smiles || candidate.formula, material_type: materialType.value }) })
  message.info(`已发送选中的候选材料（共 ${selectedCandidates.value.length} 个，取首个）到预测页面`)
}

function sendToSynthesis() {
  if (!requireSelected()) return
  const candidate = selectedCandidates.value[0]
  saveLastFormula(candidate.formula)
  router.push({ path: '/synthesis', query: withScenario({ smiles: candidate.smiles || candidate.formula, formula: candidate.formula }) })
  message.info(`已发送选中的候选材料（共 ${selectedCandidates.value.length} 个，取首个）到合成页面`)
}

function sendToExperiment() {
  if (!requireSelected()) return
  const candidate = selectedCandidates.value[0]
  saveLastFormula(candidate.formula)
  router.push({ path: '/experiments', query: withScenario({ formula: candidate.formula }) })
  message.info(`已发送选中的候选材料（共 ${selectedCandidates.value.length} 个，取首个）到实验页面`)
}

function sendToFormula() {
  if (!requireSelected()) return
  const candidate = selectedCandidates.value[0]
  saveLastFormula(candidate.formula)
  const target = candidate.formula || candidate.smiles || candidate.name
  router.push({ path: '/formula-design', query: withScenario({ target, formula: candidate.formula, smiles: candidate.smiles }) })
  message.info(`已发送选中的候选材料（共 ${selectedCandidates.value.length} 个，取首个）到配方页面`)
}

function sendToSample() {
  if (!requireSelected()) return
  const candidate = selectedCandidates.value[0]
  const name = candidate.formula || candidate.name || candidate.candidate_id
  router.push({
    path: '/samples',
    query: withScenario({
      candidate_id: candidate.candidate_id,
      source_type: 'candidate',
      name: name,
    }),
  })
  message.info(`已发送选中的候选材料（共 ${selectedCandidates.value.length} 个，取首个）到样品管理页面`)
}

// 原料可得性检查
const availabilityVisible = ref(false)
const availabilityLoading = ref(false)
const availabilityResults = ref([])

// MDM 单位符号（mass 维度）
const { symbols: unitSymbols, load: loadUnitSymbols, get: getUnitSymbol } = useUnitSymbols()
const massUnit = computed(() => getUnitSymbol('mass'))

const availabilityColumns = computed(() => [
  { title: '物料编码', dataIndex: 'material_id', key: 'material_id', width: 100 },
  { title: '名称', dataIndex: 'name', key: 'name', width: 140 },
  { title: '分类', dataIndex: 'category', key: 'category', width: 120 },
  { title: `库存(${massUnit.value})`, dataIndex: 'inventory_quantity', key: 'inventory_quantity', width: 100, align: 'right' },
  { title: `单价(¥/${massUnit.value})`, dataIndex: 'unit_cost', key: 'unit_cost', width: 110, align: 'right' },
  { title: '供应商', dataIndex: 'supplier', key: 'supplier', width: 120 },
  { title: '可得性', key: 'in_stock', width: 110 },
])

function statusColor(status) {
  return { in_stock: 'green', partial_in_stock: 'orange', no_match: 'red' }[status] || 'default'
}

function statusLabel(status) {
  return { in_stock: '已入库', partial_in_stock: '部分入库', no_match: '需新采购' }[status] || status
}

async function checkAvailability() {
  if (!requireSelected()) return
  availabilityLoading.value = true
  availabilityVisible.value = true
  try {
    const candidates = selectedCandidates.value.map((c) => ({
      candidate_id: c.candidate_id || c.formula || c.smiles || c.name,
      formula: c.formula || '',
      smiles: c.smiles || c.monomer_smiles?.[0] || '',
      name: c.name || c.formula || '',
    }))
    const res = await checkMaterialsAvailability(candidates, 1.0)
    availabilityResults.value = res.results || []
  } catch {
    availabilityResults.value = []
  } finally {
    availabilityLoading.value = false
  }
}

// 保存用户输入到 sessionStorage
watch(
  () => crystalForm.target,
  (val) => {
    if (val) sessionStorage.setItem(LAST_CRYSTAL_TARGET_KEY, val)
  }
)
watch(
  () => polymerForm.target,
  (val) => {
    if (val) sessionStorage.setItem(LAST_POLYMER_TARGET_KEY, val)
  }
)

async function onCrystalSubmit() {
  try {
    const elements = crystalForm.elements.length ? crystalForm.elements : parseFormula(crystalForm.target)

    // 多目标模式：构建 target_properties 配置数组
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
      await discoveryStore.findCrystal({
        target: crystalForm.target,
        elements,
        num_candidates: crystalForm.num_candidates,
        target_properties: targetProperties,
        scenario_id: currentScenarioId.value,
      })
    } else {
      await discoveryStore.findCrystal({
        target: crystalForm.target,
        target_property: crystalForm.target_property,
        elements,
        num_candidates: crystalForm.num_candidates,
        scenario_id: currentScenarioId.value,
      })
    }
    message.success(`发现 ${discoveryStore.crystalCandidates.length} 个晶体候选材料`)
  } catch {
    /* handled by interceptor */
  }
}

async function onPolymerSubmit() {
  try {
    // 多目标模式：构建 target_properties 配置数组
    if (polymerForm.optimize_mode === 'multi' && polymerForm.multi_objective_props.length > 0) {
      const targetProperties = polymerForm.multi_objective_props.map((prop) => {
        const cfg = polymerMultiObjectiveConfig[prop] || { weight: 0.5, direction: 'maximize', min: null, max: null }
        return {
          property: prop,
          weight: cfg.weight,
          direction: cfg.direction,
          min: cfg.min,
          max: cfg.max,
        }
      })
      await discoveryStore.findPolymer({
        target: polymerForm.target,
        num_candidates: polymerForm.num_candidates,
        target_properties: targetProperties,
        scenario_id: currentScenarioId.value,
      })
    } else {
      await discoveryStore.findPolymer({ ...polymerForm, scenario_id: currentScenarioId.value })
    }
    message.success(`发现 ${discoveryStore.polymerCandidates.length} 个聚合物候选材料`)
  } catch {
    /* handled by interceptor */
  }
}

// --- 生成模式 ---

const generatedColumns = computed(() => {
  if (genForm.mode === 'molecule') {
    return [
      { title: '2D 结构', key: 'structure', width: 140, fixed: 'left' },
      { title: 'SMILES', dataIndex: 'smiles', key: 'smiles', ellipsis: true },
      { title: '置信度', key: 'confidence', width: 180 },
      { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    ]
  }
  return [
    { title: '化学式', dataIndex: 'formula', key: 'formula', width: 160, fixed: 'left' },
    { title: '空间群', dataIndex: 'space_group', key: 'space_group', width: 120 },
    { title: '置信度', key: 'confidence', width: 180 },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
  ]
})

// 为生成结果注入唯一行 key，避免相同 smiles/formula 导致渲染/选择异常
const generatedTableData = computed(() =>
  discoveryStore.generatedCandidates.map((r, index) => {
    const baseKey = r.smiles || r.formula || 'row'
    return { ...r, _rowKey: `${baseKey}-${index}` }
  })
)

function confidenceColor(conf) {
  // 统一走 CSS 变量语义色：低置信度=警告橙、高=成功绿、中=主色橙
  if (conf < 0.7) return 'var(--warning)'
  if (conf >= 0.9) return 'var(--success)'
  return 'var(--primary)'
}

async function onGenerateSubmit() {
  try {
    const constraints = {
      elements: genForm.elements,
      max_atoms: genForm.max_atoms,
    }
    if (genForm.mode === 'molecule') {
      constraints.target_property = genForm.target_property
    } else {
      constraints.space_groups = genForm.space_groups
        ? genForm.space_groups.split(',').map((s) => s.trim()).filter(Boolean)
        : []
    }
    await discoveryStore.generate({
      mode: genForm.mode,
      constraints,
      count: genForm.count,
    })
    message.success(`生成 ${discoveryStore.generatedCandidates.length} 个候选材料`)
  } catch {
    /* handled by interceptor */
  }
}

// --- 并行假设验证（Idea Parallel Verify）---

const ideas = ref([])
const ideasLoading = ref(false)
const selectedIdeaIds = ref([])
const verifying = ref(false)
const verifyTaskIds = ref([])
const verifyResults = ref([])

const createIdeaVisible = ref(false)
const creating = ref(false)
const createForm = reactive({
  name: '',
  material_type: 'molecule',
  smiles: '',
  formula: '',
  target_properties: [],
  notes: '',
})

// 可选目标属性（合并晶体与聚合物预测器支持的属性），优先从 MDM 主数据加载
const ideaPropertyOptions = ref([
  { label: '离子电导率', value: 'ionic_conductivity' },
  { label: '带隙', value: 'band_gap' },
  { label: '形成能', value: 'formation_energy' },
  { label: '体积模量', value: 'bulk_modulus' },
  { label: '剪切模量', value: 'shear_modulus' },
  { label: '能量高于凸包', value: 'e_above_hull' },
  { label: '玻璃化转变温度', value: 'glass_transition_temp' },
  { label: '介电常数', value: 'dielectric_constant' },
  { label: '弹性模量', value: 'elastic_modulus' },
  { label: '热导率', value: 'thermal_conductivity' },
  { label: '分解温度', value: 'decomposition_temp' },
])

// IDEA 状态选项，优先从 MDM 主数据加载
const ideaStatusOptions = ref([
  { label: '草稿', value: 'draft' },
  { label: '验证中', value: 'verifying' },
  { label: '已验证', value: 'verified' },
  { label: '失败', value: 'failed' },
  { label: '优选', value: 'preferred' },
  { label: '已淘汰', value: 'eliminated' },
])

const ideaColumns = [
  { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '材料类型', dataIndex: 'material_type', key: 'material_type', width: 110 },
  { title: 'SMILES/Formula', key: 'identifier', width: 200, ellipsis: true },
  { title: '状态', dataIndex: 'status', key: 'status', width: 90 },
  { title: '评分', dataIndex: 'score', key: 'score', width: 80 },
  { title: '操作', key: 'actions', width: 120 },
]

function ideaStatusColor(status) {
  return {
    draft: 'default',
    verifying: 'processing',
    verified: 'success',
    failed: 'error',
    preferred: 'gold',
    eliminated: 'default',
  }[status] || 'default'
}

function ideaStatusLabel(status) {
  const opt = ideaStatusOptions.value.find((o) => o.value === status)
  return opt ? opt.label : status
}

function addTargetProp() {
  createForm.target_properties.push({ name: '', direction: 'maximize', target_value: null })
}

function showCreateIdeaModal() {
  createForm.name = ''
  createForm.material_type = 'molecule'
  createForm.smiles = ''
  createForm.formula = ''
  createForm.target_properties = []
  createForm.notes = ''
  createIdeaVisible.value = true
}

async function onCreateIdea() {
  if (!createForm.name.trim()) {
    message.warning('请填写名称')
    return
  }
  creating.value = true
  try {
    await createIdea({
      name: createForm.name,
      material_type: createForm.material_type,
      smiles: createForm.smiles,
      formula: createForm.formula,
      target_properties: createForm.target_properties.filter((tp) => tp.name),
      notes: createForm.notes,
    })
    message.success('IDEA 创建成功')
    createIdeaVisible.value = false
    await loadIdeas()
  } catch {
    /* handled by interceptor */
  } finally {
    creating.value = false
  }
}

function onSelectIdeas(keys) {
  selectedIdeaIds.value = keys
}

async function loadIdeas() {
  ideasLoading.value = true
  try {
    ideas.value = await listIdeas()
  } catch {
    /* handled by interceptor */
  } finally {
    ideasLoading.value = false
  }
}

function getIdeaName(id) {
  const idea = ideas.value.find((i) => i.idea_id === id)
  return idea ? idea.name : id
}

function getIdeaStatus(id) {
  const idea = ideas.value.find((i) => i.idea_id === id)
  return idea ? idea.status : ''
}

async function onParallelVerify() {
  if (selectedIdeaIds.value.length === 0) return
  verifying.value = true
  verifyTaskIds.value = [...selectedIdeaIds.value]
  verifyResults.value = []
  try {
    const res = await parallelVerifyIdeas(selectedIdeaIds.value)
    verifyResults.value = res.results || []
    message.success(`并行验证完成：${verifyResults.value.length} 个结果`)
    await loadIdeas()
  } catch {
    /* handled by interceptor */
  } finally {
    verifying.value = false
  }
}

function getVerifyProgress(id) {
  if (verifying.value) return 30
  const res = verifyResults.value.find((r) => r.idea_id === id)
  return res ? 100 : 0
}

function getVerifyProgressStatus(id) {
  if (verifying.value) return 'active'
  const res = verifyResults.value.find((r) => r.idea_id === id)
  if (!res) return 'normal'
  return res.status === 'verified' ? 'success' : 'exception'
}

function getVerifyResultColor(id) {
  const res = verifyResults.value.find((r) => r.idea_id === id)
  if (!res) return 'default'
  return ideaStatusColor(res.status)
}

function getVerifyResultStatus(id) {
  const res = verifyResults.value.find((r) => r.idea_id === id)
  if (!res) return ''
  return ideaStatusLabel(res.status)
}

async function markIdeaStatus(id, status) {
  try {
    await updateIdeaStatus(id, { status })
    message.success(`已标记为${ideaStatusLabel(status)}`)
    await loadIdeas()
    // 同步更新 verifyResults 中的状态显示
    const res = verifyResults.value.find((r) => r.idea_id === id)
    if (res) res.status = status
  } catch {
    /* handled by interceptor */
  }
}

// 数据刷新后清空旧的选择，避免 key/记录不匹配
watch(
  () => currentData.value,
  () => {
    selectedCandidates.value = []
    selectedCandidateKeys.value = []
  }
)

// 切换到并行验证 Tab 时自动加载 IDEA 列表
watch(
  () => materialType.value,
  (val) => {
    if (val === 'verify' && ideas.value.length === 0) {
      loadIdeas()
    }
  }
)
</script>

<style scoped>
.discovery {
  width: 100%;
  max-width: 100%;
}

.input-card,
.result-card,
.empty-card {
  background: var(--light-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-card);
  margin-bottom: 16px;
}

.input-card :deep(.ant-card-body) {
  padding: 8px 24px 20px;
}

.input-card :deep(.ant-tabs-nav) {
  margin-bottom: 16px;
}

.input-card :deep(.ant-input-number-input) {
  font-variant-numeric: tabular-nums;
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

.input-hint {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-muted);
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

/* 折叠后内部的编辑器去除外层 margin 与背景，避免双层卡片视觉 */
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

.empty-card :deep(.ant-card-body) {
  padding: 56px 0;
}

.empty-icon {
  font-size: 56px;
  color: var(--text-muted);
  opacity: 0.4;
}

.empty-card :deep(.ant-empty-description) {
  color: var(--text-muted);
  font-size: 13px;
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
  color: var(--warning);
  font-weight: 500;
}

/* 并行验证面板 */
.verify-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.idea-table {
  margin-bottom: 16px;
}

.verify-board,
.verify-results {
  margin-top: 16px;
  padding: 12px 16px;
  background: var(--light-bg-hover, #fafafa);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: 8px;
}

.board-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin-bottom: 12px;
}

.verify-task-item {
  padding: 8px 12px;
  background: var(--light-bg-card, #fff);
  border: 1px solid var(--border, #e8e8e8);
  border-radius: 6px;
}

.task-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.task-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1a1a2e);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-card-item {
  height: 100%;
}

.result-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.result-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-score {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 4px 0;
}

.score-label {
  font-size: 12px;
  color: var(--text-muted, #8c8c8c);
}

.prop-row {
  padding: 4px 0;
}

.prop-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2px;
}

.prop-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #595959);
}

.prop-values {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-muted, #8c8c8c);
  font-variant-numeric: tabular-nums;
}

.prop-target {
  color: var(--text-secondary, #595959);
}

.result-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
}

.target-prop-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
}

/* 生成模式结果 */
.confidence-legend {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 400;
}

.legend-green {
  color: var(--success);
  font-weight: 500;
}

.legend-orange {
  color: var(--warning);
  font-weight: 500;
}

.confidence-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.confidence-cell :deep(.ant-progress) {
  flex: 1;
  min-width: 80px;
}

.confidence-value {
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
</style>
