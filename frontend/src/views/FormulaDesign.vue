<template>
  <div class="formula-design-page">
    <!-- 页面头部 -->
    <div class="page-header page-header-row">
      <div>
        <h1 class="page-title">配方与工艺</h1>
        <p class="page-subtitle">配方版本管理、BOM/BOP 设计与成本核算</p>
      </div>
      <div class="header-actions">
        <a-button type="primary" @click="openDesignDrawer">
          <template #icon><PlusOutlined /></template>
          生成新配方
        </a-button>
      </div>
    </div>

    <!-- 从候选合成路径进入时的状态提示 -->
    <a-alert
      v-if="routeBomInfo"
      :type="routeBomLoading ? 'info' : 'success'"
      show-icon
      closable
      :message="routeBomLoading
        ? `已选合成路径 ${routeBomInfo.route_label}，正在生成/打开 BOM 草案…`
        : `已基于合成路径 ${routeBomInfo.route_label} 生成 BOM 草案，可在详情中编辑保存`"
      style="margin-bottom: 12px"
      @close="routeBomInfo = null"
    >
      <template #action>
        <a-spin v-if="routeBomLoading" size="small" />
      </template>
    </a-alert>

    <!-- 配方列表 -->
    <a-card :bordered="false" class="list-card">
      <!-- 筛选栏 -->
      <div class="filter-bar">
        <span class="filter-label">项目：</span>
        <a-select
          v-model:value="filterProjectId"
          size="small"
          style="width: 180px"
          allow-clear
          placeholder="全部项目"
          :options="projectOptions"
          :loading="projectCtx.loading"
        />
        <span class="filter-label" style="margin-left: 12px">来源：</span>
        <a-select
          v-model:value="filterSource"
          size="small"
          style="width: 140px"
          allow-clear
          placeholder="全部来源"
          @change="onFilterChange"
        >
          <a-select-option value="">全部来源</a-select-option>
          <a-select-option value="candidate_bom">候选BOM</a-select-option>
          <a-select-option value="formula">配方设计</a-select-option>
        </a-select>
        <span class="filter-label" style="margin-left: 12px">目标材料：</span>
        <a-input
          v-model:value="filterTarget"
          size="small"
          style="width: 200px"
          allow-clear
          placeholder="按目标材料筛选"
          @change="onFilterChange"
        />
        <a-button size="small" style="margin-left: 12px" @click="resetFilter">重置</a-button>
        <span class="filter-stats">共 {{ filteredFormulaList.length }} 条</span>
      </div>
      <a-spin :spinning="formulaListLoading">
        <EmptyState v-if="!formulaListLoading && formulaList.length === 0" type="create" description="暂无配方版本，点击右上角生成新配方" action-text="生成新配方" @action="openDesignDrawer" />
        <a-table
          v-else
          :columns="formulaListColumns"
          :data-source="filteredFormulaList"
          size="middle"
          :pagination="{ pageSize: 10, size: 'small', showTotal: (t) => `共 ${t} 条` }"
          row-key="version_id"
          :scroll="{ x: 980 }"
          class="formula-table"
          :custom-row="onRowClick"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'formula_id'">
              <span class="formula-id-text">{{ record.formula_id }}</span>
              <a-tag v-if="record.is_active" color="green" size="small" style="margin-left: 6px">活跃</a-tag>
            </template>
            <template v-else-if="column.key === 'source'">
              <a-tag v-if="record.source === 'candidate_bom'" color="orange" size="small">候选BOM</a-tag>
              <a-tag v-else color="blue" size="small">配方设计</a-tag>
            </template>
            <template v-else-if="column.key === 'version'">
              V{{ record.version_number.toString().padStart(2, '0') }}
            </template>
            <template v-else-if="column.key === 'bom_count'">
              {{ (record.bom || []).length }} 项
            </template>
            <template v-else-if="column.key === 'total_cost_per_kg'">
              ¥{{ Number(record.total_cost_per_kg || 0).toFixed(2) }}
            </template>
            <template v-else-if="column.key === 'created_at'">
              <span class="text-muted">{{ formatTime(record.created_at) }}</span>
            </template>
            <template v-else-if="column.key === 'actions'">
              <a-button size="small" type="link" @click.stop="openDetail(record)">详情</a-button>
              <a-button v-if="record.source !== 'candidate_bom'" size="small" type="link" @click.stop="onViewHistory(record)">历史</a-button>
            </template>
          </template>
        </a-table>
      </a-spin>
    </a-card>

    <!-- 配方详情抽屉 -->
    <a-drawer
      :open="detailVisible"
      :width="820"
      title="配方详情"
      placement="right"
      @update:open="(v) => (detailVisible = v)"
    >
      <a-spin :spinning="detailLoading">
        <div v-if="currentFormula" class="detail-content">
          <!-- 头部信息 -->
          <div class="detail-head">
            <div class="head-left">
              <div class="head-title">
                {{ currentFormula.formula_id }}
                <a-tag color="blue">V{{ currentFormula.version_number.toString().padStart(2, '0') }}</a-tag>
                <a-tag v-if="currentFormula.is_active" color="green">活跃</a-tag>
              </div>
              <div class="head-sub">目标材料：{{ currentFormula.target_material || '—' }}</div>
              <div class="head-sub">需求量：{{ currentFormula.quantity_kg }} {{ massUnit }}</div>
            </div>
            <div class="head-actions">
              <a-button v-if="currentFormula.source !== 'candidate_bom'" size="small" @click="onSaveFormula">保存新版本</a-button>
              <a-button
                v-if="currentFormula.source !== 'candidate_bom' && !currentFormula.is_active"
                size="small"
                type="primary"
                @click="onActivateVersion(currentFormula)"
              >设为活跃</a-button>
              <a-button v-if="currentFormula.source !== 'candidate_bom'" size="small" @click="onPrepareSample">制备样品</a-button>
              <!-- 候选 BOM 编辑状态机：默认只读，点击编辑后可修改 -->
              <a-button
                v-if="isCandidateBom && !isEditing"
                size="small"
                type="primary"
                @click="onStartEdit"
              >编辑</a-button>
              <template v-if="isCandidateBom && isEditing">
                <a-button
                  size="small"
                  type="primary"
                  :loading="savingBom"
                  @click="onSaveCandidateBom"
                >保存修改</a-button>
                <a-button size="small" @click="onCancelEdit">取消</a-button>
              </template>
              <a-tag v-if="currentFormula.source === 'candidate_bom'" :color="isEditing ? 'orange' : 'default'">{{ isEditing ? '编辑中' : '只读' }}</a-tag>
            </div>
          </div>

          <!-- 成本概览 -->
          <a-row :gutter="12" class="cost-row">
            <a-col :span="8">
              <a-card size="small" class="kpi-card">
                <a-statistic title="物料成本" :value="currentFormula.material_cost || 0" prefix="¥" :precision="2" />
              </a-card>
            </a-col>
            <a-col :span="8">
              <a-card size="small" class="kpi-card">
                <a-statistic title="加工成本" :value="currentFormula.process_cost || 0" prefix="¥" :precision="2" />
              </a-card>
            </a-col>
            <a-col :span="8">
              <a-card size="small" class="kpi-card">
                <a-statistic :title="`总成本 (¥/${massUnit})`" :value="currentFormula.total_cost_per_kg || 0" prefix="¥" :precision="2" />
              </a-card>
            </a-col>
          </a-row>

          <!-- P1-2：AI 生成配方的可信度元信息（置信度/假设/证据/复核） -->
          <AIOutputMeta
            v-if="currentFormula.ai_meta && currentFormula.ai_meta.confidence != null"
            :confidence="currentFormula.ai_meta.confidence"
            :agent-name="currentFormula.ai_meta.agent_name || ''"
            :strategy="currentFormula.ai_meta.strategy || ''"
            :assumptions="currentFormula.ai_meta.key_assumptions || []"
            :evidence-sources="currentFormula.ai_meta.evidence_sources || []"
            :human-review-required="!!currentFormula.ai_meta.human_review_required"
            style="margin-bottom: 12px"
          />

          <!-- 配方详情Tab -->
          <a-tabs v-model:activeKey="formulaDetailTab" size="small" class="formula-detail-tabs">
            <a-tab-pane key="bom" tab="物料清单 (BOM)">
              <div class="section-block">
                <div class="section-title">
                  物料清单 (BOM)
                  <a-button v-if="isCandidateBom && isEditing" size="small" type="link" @click="onAddBomRow">+ 新增物料</a-button>
                </div>
            <a-table
              :columns="bomColumns"
              :data-source="currentFormula.bom || []"
              size="small"
              :pagination="false"
              :row-key="contentRowKey"
            >
              <template #bodyCell="{ column, record, index }">
                <template v-if="column.key === 'name'">
                  <a-input
                    v-if="isCandidateBom && isEditing"
                    v-model:value="record.material_name"
                    size="small"
                  />
                  <span v-else>{{ record.material_name || '-' }}</span>
                </template>
                <template v-else-if="column.key === 'amount'">
                  <a-input-number
                    v-if="isCandidateBom && isEditing"
                    v-model:value="record.amount_kg"
                    :min="0"
                    :step="0.1"
                    size="small"
                    style="width: 90px"
                    @change="onBomAmountChange(record)"
                  />
                  <span v-else>{{ record.amount_kg ?? '-' }}</span>
                </template>
                <template v-else-if="column.key === 'price'">
                  <a-input-number
                    v-if="isCandidateBom && isEditing"
                    v-model:value="record.unit_price"
                    :min="0"
                    :step="0.1"
                    size="small"
                    style="width: 100px"
                    @change="onBomAmountChange(record)"
                  />
                  <span v-else>{{ record.unit_price ?? '-' }}</span>
                </template>
                <template v-else-if="column.key === 'cost'">
                  ¥{{ Number(record.cost || 0).toFixed(2) }}
                </template>
                <template v-else-if="column.key === 'in_stock'">
                  <a-tag v-if="record.in_stock" color="green">已入库</a-tag>
                  <a-tag v-else color="orange">需采购</a-tag>
                </template>
                <template v-else-if="column.key === 'bom_op' && isCandidateBom && isEditing">
                  <a-button size="small" type="link" danger @click="onRemoveBomRow(index)">删除</a-button>
                </template>
              </template>
            </a-table>
              </div>
            </a-tab-pane>

            <a-tab-pane key="bop" tab="工艺参数 (BOP)">
              <div class="section-block">
                <div class="section-title">
                  工艺参数 (BOP)
                  <a-button v-if="isCandidateBom && isEditing" size="small" type="link" @click="onAddBopRow">+ 新增步骤</a-button>
                </div>
            <a-table
              :columns="bopColumns"
              :data-source="currentFormula.bop || []"
              size="small"
              :pagination="false"
              :row-key="contentRowKey"
            >
              <template #bodyCell="{ column, record, index }">
                <template v-if="column.key === 'step'">
                  <a-input
                    v-if="isCandidateBom && isEditing"
                    v-model:value="record.step"
                    size="small"
                  />
                  <span v-else>{{ record.step || '-' }}</span>
                </template>
                <template v-else-if="column.key === 'equipment'">
                  <a-input
                    v-if="isCandidateBom && isEditing"
                    v-model:value="record.equipment"
                    size="small"
                  />
                  <template v-else>
                    <span>{{ record.equipment || '-' }}</span>
                    <a-tooltip v-if="record.equipment && !isEquipmentValid(record.equipment)" title="点击快速登记到设备台账">
                      <a-tag
                        color="orange"
                        size="small"
                        style="margin-left: 4px; cursor: pointer"
                        @click="openEquipmentQuickRegister(record.equipment)"
                      >
                        未入账 · 点击登记
                      </a-tag>
                    </a-tooltip>
                  </template>
                </template>
                <template v-else-if="column.key === 'temp'">
                  <a-input-number
                    v-if="isCandidateBom && isEditing"
                    v-model:value="record.temperature"
                    :step="1"
                    size="small"
                    style="width: 90px"
                  />
                  <span v-else>{{ record.temperature ?? '-' }}</span>
                </template>
                <template v-else-if="column.key === 'duration'">
                  <a-input-number
                    v-if="isCandidateBom && isEditing"
                    v-model:value="record.duration_h"
                    :min="0"
                    :step="0.1"
                    size="small"
                    style="width: 80px"
                  />
                  <span v-else>{{ record.duration_h ?? '-' }}</span>
                </template>
                <template v-else-if="column.key === 'params'">
                  <a-input
                    v-if="isCandidateBom && isEditing"
                    v-model:value="record.key_params"
                    size="small"
                  />
                  <span v-else>{{ record.key_params || '-' }}</span>
                </template>
                <template v-else-if="column.key === 'bop_op' && isCandidateBom && isEditing">
                  <a-button size="small" type="link" danger @click="onRemoveBopRow(index)">删除</a-button>
                </template>
              </template>
            </a-table>
              </div>
            </a-tab-pane>

            <a-tab-pane key="knowledge" tab="相关知识">
              <div class="section-block">
                <MaterialKnowledgeCard
                  v-if="currentFormula && currentFormula.target_material"
                  :query="currentFormula.target_material"
                  :limit="5"
                />
                <EmptyState
                  v-else
                  type="data"
                  description="暂无相关知识数据"
                />
              </div>
            </a-tab-pane>
          </a-tabs>

          <!-- 加工成本明细 -->
          <a-collapse
            v-if="currentFormula.process_cost_breakdown?.length"
            :bordered="false"
            class="cost-breakdown-collapse"
          >
            <a-collapse-panel key="breakdown" header="加工成本明细（设备折旧 / 能耗 / 人工）">
              <a-table
                :columns="costBreakdownColumns"
                :data-source="currentFormula.process_cost_breakdown"
                size="small"
                :pagination="false"
                :row-key="contentRowKey"
              />
              <div class="cost-model-hint">
                成本模型：折旧按设备台时费（搅拌/混料 80、涂布 120、烘箱 50 元/h，未识别设备 100 元/h）；
                能耗按工艺温度估算功率 × 工业电价 0.8 元/kWh；人工 60 元/h。
              </div>
            </a-collapse-panel>
          </a-collapse>

          <!-- EHS 合规 -->
          <div class="section-block">
            <div class="section-title">EHS 合规检查</div>
            <a-descriptions size="small" :column="2" bordered>
              <a-descriptions-item label="REACH 合规">{{ currentFormula.ehs?.reach || '未检测' }}</a-descriptions-item>
              <a-descriptions-item label="GHS 危险性分类">{{ currentFormula.ehs?.ghs_classification || currentFormula.ehs?.hazard_class || '未检测' }}</a-descriptions-item>
              <a-descriptions-item label="存储要求">{{ currentFormula.ehs?.storage || '未检测' }}</a-descriptions-item>
              <a-descriptions-item label="废弃处理">{{ currentFormula.ehs?.disposal || '未检测' }}</a-descriptions-item>
            </a-descriptions>
            <a-table
              v-if="currentFormula.ehs?.hazard_profiles?.length"
              :columns="hazardColumns"
              :data-source="currentFormula.ehs.hazard_profiles"
              size="small"
              :pagination="false"
              :row-key="contentRowKey"
              style="margin-top: 8px"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'reach_status'">
                  <a-tag :color="record.reach_status === '通过' ? 'green' : (record.reach_status === '未通过' ? 'red' : 'default')">
                    {{ record.reach_status }}
                  </a-tag>
                </template>
                <template v-else-if="column.key === 'sds_link'">
                  <a v-if="record.sds_link" :href="record.sds_link" target="_blank" rel="noopener">SDS 文档</a>
                  <span v-else class="text-muted">未关联</span>
                </template>
              </template>
            </a-table>
          </div>
        </div>
      </a-spin>
    </a-drawer>

    <!-- 生成新配方抽屉 -->
    <a-drawer
      :open="designVisible"
      title="生成新配方"
      placement="right"
      width="720"
      @update:open="(v) => (designVisible = v)"
    >
      <a-form layout="vertical" size="small">
        <div class="design-agent-bar">
          <span class="design-agent-label">执行智能体：</span>
          <AgentChip
            agent-id="builtin_industrialization"
            fallback-name="配方工艺师"
            fallback-desc="负责 BOM/BOP 配方设计、物料成本核算与合规审查"
          />
        </div>
        <a-form-item label="目标材料">
          <a-select
            v-model:value="target"
            show-search
            allow-clear
            placeholder="从物料库选择或输入材料名称/SMILES"
            :options="targetOptions"
            :filter-option="filterOption"
          />
        </a-form-item>
        <a-form-item :label="`需求量 (${massUnit})`">
          <a-input-number v-model:value="quantity" :min="0.1" :step="1" style="width: 160px" />
          <a-select
            v-model:value="quantityPreset"
            size="small"
            style="width: 180px; margin-left: 8px"
            placeholder="常用批量"
            allow-clear
            :options="batchPresets"
            @change="onPresetChange"
          />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" :loading="loading" @click="onDesign">生成配方</a-button>
        </a-form-item>
      </a-form>

      <a-spin :spinning="loading">
        <EmptyState v-if="!result" type="data" description="输入目标材料后点击生成配方" />
        <template v-else>
          <!-- P1-2：AI 生成配方的可信度元信息（置信度/假设/证据/复核） -->
          <AIOutputMeta
            v-if="result.ai_meta && result.ai_meta.confidence != null"
            :confidence="result.ai_meta.confidence"
            :agent-name="result.ai_meta.agent_name || ''"
            :strategy="result.ai_meta.strategy || ''"
            :assumptions="result.ai_meta.key_assumptions || []"
            :evidence-sources="result.ai_meta.evidence_sources || []"
            :human-review-required="!!result.ai_meta.human_review_required"
            style="margin-bottom: 12px"
          />
          <!-- BOM -->
          <div class="section-block">
            <div class="section-title">物料清单 (BOM)</div>
            <a-table
              :columns="bomColumns"
              :data-source="result.bom || []"
              size="small"
              :pagination="false"
              :row-key="contentRowKey"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'cost'">
                  ¥{{ Number(record.cost || 0).toFixed(2) }}
                </template>
                <template v-else-if="column.key === 'in_stock'">
                  <a-tag v-if="record.in_stock" color="green">已入库</a-tag>
                  <a-tag v-else color="orange">需采购</a-tag>
                </template>
              </template>
            </a-table>
          </div>

          <!-- BOP -->
          <div class="section-block">
            <div class="section-title">工艺参数 (BOP)</div>
            <a-table
              :columns="bopColumns"
              :data-source="result.bop || []"
              size="small"
              :pagination="false"
              :row-key="contentRowKey"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'equipment'">
                  <span>{{ record.equipment || '-' }}</span>
                  <a-tooltip v-if="record.equipment && !isEquipmentValid(record.equipment)" title="点击快速登记到设备台账">
                    <a-tag
                      color="orange"
                      size="small"
                      style="margin-left: 4px; cursor: pointer"
                      @click="openEquipmentQuickRegister(record.equipment)"
                    >
                      未入账 · 点击登记
                    </a-tag>
                  </a-tooltip>
                </template>
              </template>
            </a-table>
          </div>

          <!-- 成本概览 -->
          <a-row :gutter="12" class="cost-row">
            <a-col :span="8">
              <a-statistic title="物料成本" :value="result.material_cost || 0" prefix="¥" :precision="2" />
            </a-col>
            <a-col :span="8">
              <a-statistic title="加工成本" :value="result.process_cost || 0" prefix="¥" :precision="2" />
            </a-col>
            <a-col :span="8">
              <a-statistic :title="`总成本 (¥/${massUnit})`" :value="result.total_cost_per_kg || 0" prefix="¥" :precision="2" />
            </a-col>
          </a-row>

          <!-- EHS -->
          <div class="section-block">
            <div class="section-title">EHS 合规</div>
            <a-descriptions size="small" :column="2" bordered>
              <a-descriptions-item label="REACH 合规">{{ result.ehs?.reach || '未检测' }}</a-descriptions-item>
              <a-descriptions-item label="GHS 分类">{{ result.ehs?.ghs_classification || result.ehs?.hazard_class || '未检测' }}</a-descriptions-item>
              <a-descriptions-item label="存储要求">{{ result.ehs?.storage || '未检测' }}</a-descriptions-item>
              <a-descriptions-item label="废弃处理">{{ result.ehs?.disposal || '未检测' }}</a-descriptions-item>
            </a-descriptions>
          </div>

          <!-- 保存操作 -->
          <div class="design-actions">
            <a-button type="primary" :loading="saveSubmitting" @click="onSaveFormula">
              保存为配方版本
            </a-button>
          </div>
        </template>
      </a-spin>
    </a-drawer>

    <!-- 保存配方版本抽屉 -->
    <a-drawer
      :open="saveModalVisible"
      title="保存配方版本"
      placement="right"
      width="480"
      :z-index="1001"
      @update:open="(v) => (saveModalVisible = v)"
    >
      <a-form layout="vertical" size="small">
        <a-form-item label="当前目标材料">
          <span>{{ target || currentFormula?.target_material || '—' }}</span>
        </a-form-item>
        <a-form-item label="变更说明">
          <a-textarea
            v-model:value="changeSummary"
            :rows="3"
            placeholder="如：调整锂盐比例以提升离子电导率…"
          />
        </a-form-item>
        <a-alert
          v-if="currentFormulaId"
          type="info"
          :message="`将保存为配方 ${currentFormulaId} 的新版本`"
          show-icon
        />
        <a-alert
          v-else
          type="info"
          message="将创建新配方编号并保存为首版本"
          show-icon
        />
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="saveSubmitting" @click="saveModalVisible = false">取消</a-button>
          <a-button type="primary" :loading="saveSubmitting" @click="submitSaveFormula">保存</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 配方历史版本抽屉 -->
    <a-drawer
      :open="historyModalVisible"
      :title="`配方 ${historyFormulaId} 历史版本`"
      placement="right"
      width="720"
      :z-index="1001"
      @update:open="(v) => (historyModalVisible = v)"
    >
      <a-spin :spinning="historyLoading">
        <a-table
          :columns="historyColumns"
          :data-source="historyVersions"
          size="small"
          :pagination="false"
          row-key="version_id"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'version'">
              V{{ record.version_number.toString().padStart(2, '0') }}
            </template>
            <template v-else-if="column.key === 'total_cost_per_kg'">
              ¥{{ Number(record.total_cost_per_kg || 0).toFixed(2) }}
            </template>
            <template v-else-if="column.key === 'actions'">
              <a-space>
                <a-button size="small" type="link" @click="openDetail(record)">查看</a-button>
                <a-button
                  v-if="!record.is_active"
                  size="small"
                  type="link"
                  @click="onActivateVersion(record)"
                >设为活跃</a-button>
                <a-tag v-else color="green">当前活跃</a-tag>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-spin>
    </a-drawer>

    <!-- 设备快速登记弹窗 -->
    <a-modal
      v-model:open="equipModalVisible"
      title="快速登记设备"
      :confirm-loading="equipSubmitting"
      ok-text="登记入账"
      cancel-text="取消"
      @ok="submitEquipmentQuickRegister"
    >
      <a-form layout="vertical" size="small">
        <a-form-item label="设备名称" required>
          <a-input v-model:value="equipForm.name" placeholder="设备名称" />
        </a-form-item>
        <a-form-item label="规格型号">
          <a-input v-model:value="equipForm.model" placeholder="如 5L 双行星搅拌机" />
        </a-form-item>
        <a-form-item label="负责人">
          <a-input v-model:value="equipForm.responsible_person" placeholder="设备负责人" />
        </a-form-item>
        <a-form-item label="位置">
          <a-input v-model:value="equipForm.location" placeholder="如 中试车间 A 区" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useMdmDict } from '@/utils/mdmDict'
import { PlusOutlined } from '@ant-design/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import client from '@/api/client'
import { getRawMaterials } from '@/api/rawMaterials'
import { listEquipment, createEquipment } from '@/api/equipment'
import { saveFormula, listFormulas, getFormula, getFormulaHistory, activateFormulaVersion } from '@/api/formula'
import AgentChip from '@/components/AgentChip.vue'
import AIOutputMeta from '@/components/AIOutputMeta.vue'
import MaterialKnowledgeCard from '@/components/MaterialKnowledgeCard.vue'
import { useProjectContextStore } from '@/stores/projectContext'
import { useUnitSymbols } from '@/utils/mdmDict'
import EmptyState from '@/components/EmptyState.vue'
import { MESSAGES } from '@/constants/glossary'

// 单位符号（从 MDM 主数据加载）
const { symbols: unitSymbols, load: loadUnitSymbols } = useUnitSymbols()

// 常用单位符号（模板引用）
const massUnit = computed(() => unitSymbols.value.mass || 'kg')
const tempUnit = computed(() => unitSymbols.value.temperature || '°C')
const timeUnit = computed(() => unitSymbols.value.time || 'h')

const route = useRoute()
const router = useRouter()
const projectCtx = useProjectContextStore()

// ── 候选 BOM 编辑能力（0727：补全脚本，解决"不能编辑"问题）──
const savingBom = ref(false)
const isCandidateBom = computed(
  () => !!currentFormula.value && currentFormula.value.source === 'candidate_bom',
)
// 配方编辑状态机：默认只读，点击"编辑"后进入可编辑态，保存/取消后回到只读
const isEditing = ref(false)
// 编辑前的 BOM/BOP 快照，取消编辑时恢复
let _editSnapshot = null

function onStartEdit() {
  const f = currentFormula.value
  if (!f) return
  _editSnapshot = JSON.parse(JSON.stringify({
    bom: f.bom || [],
    bop: f.bop || [],
  }))
  isEditing.value = true
}

function onCancelEdit() {
  const f = currentFormula.value
  if (f && _editSnapshot) {
    f.bom = _editSnapshot.bom
    f.bop = _editSnapshot.bop
  }
  _editSnapshot = null
  isEditing.value = false
}

// ── 从候选合成路径进入：自动生成或打开 BOM 草案（0727）──
// 当从 CandidateWorkbench 携带 route_id 等参数跳转过来时启用
const routeBomInfo = ref(null) // { candidate_id, route_id, synthesis_task_id, route_label }
const routeBomLoading = ref(false)

// 归一化 route_id 用于比对：R1 / r1 / 1 视为同一条路径
function normalizeRouteId(rid) {
  if (!rid) return ''
  const s = String(rid).trim().toUpperCase()
  return s.startsWith('R') ? s.slice(1) : s
}

// 在已加载的配方列表中查找候选 BOM 是否已存在（同候选 + 同 route_id）
function findExistingCandidateBom(candidateId, routeId) {
  if (!candidateId || !routeId) return null
  const targetRid = normalizeRouteId(routeId)
  return formulaList.value.find((f) => {
    if (f.source !== 'candidate_bom') return false
    if ((f.candidate_id || '') !== candidateId) return false
    return normalizeRouteId(f.source_route_id) === targetRid
  }) || null
}

// 调用后端从合成路径生成 BOM + 工艺方案，返回新建 BOM 的 formula_id
async function generateBomFromRoute(info) {
  const url = `/candidates/${encodeURIComponent(info.candidate_id)}/bom-from-route`
  const res = await client.post(url, {
    route_id: info.route_id,
    synthesis_task_id: info.synthesis_task_id || '',
    quantity_kg: quantity.value || 1.0,
  }, { timeout: 30000 })
  // 后端返回 { bom: BomScheme, process_scheme: ProcessScheme }
  return res?.bom?.bom_id || ''
}

function onBomAmountChange(row) {
  const amt = Number(row.amount_kg || 0)
  const price = Number(row.unit_price || 0)
  row.cost = Math.round(amt * price * 100) / 100
}

function onAddBomRow() {
  if (!currentFormula.value) return
  if (!Array.isArray(currentFormula.value.bom)) currentFormula.value.bom = []
  currentFormula.value.bom.push({
    material_id: '',
    material_name: '',
    cas_number: '',
    amount_kg: 0,
    unit_price: 0,
    cost: 0,
    supplier: '',
    in_stock: false,
  })
}

function onRemoveBomRow(idx) {
  if (!currentFormula.value?.bom) return
  currentFormula.value.bom.splice(idx, 1)
}

function onAddBopRow() {
  if (!currentFormula.value) return
  if (!Array.isArray(currentFormula.value.bop)) currentFormula.value.bop = []
  currentFormula.value.bop.push({
    step: '',
    equipment: '',
    temperature: 25,
    duration_h: 0,
    key_params: '',
  })
}

function onRemoveBopRow(idx) {
  if (!currentFormula.value?.bop) return
  currentFormula.value.bop.splice(idx, 1)
}

async function onSaveCandidateBom() {
  const f = currentFormula.value
  if (!f || !f.bom_id) {
    message.warning('当前配方不是候选 BOM，无法保存')
    return
  }
  savingBom.value = true
  try {
    // 重新计算总成本
    const materialCost = (f.bom || []).reduce((s, r) => s + Number(r.cost || 0), 0)
    const processCost = (f.process_cost_breakdown || []).reduce(
      (s, r) => s + Number(r.subtotal || 0), 0,
    )
    const total = materialCost + processCost
    await client.put(`/bom/${f.bom_id}`, {
      formulation: {
        materials: f.bom || [],
        route_reactants: [],
        target_smiles: '',
      },
      process_route: {
        steps: f.bop || [],
        ehs: f.ehs || {},
        material_cost: materialCost,
        process_cost: processCost,
        total_cost_per_kg: total,
        process_cost_breakdown: f.process_cost_breakdown || [],
      },
    })
    message.success('BOM 修改已保存')
    // 保存成功后退出编辑态
    isEditing.value = false
    _editSnapshot = null
    // 刷新详情与列表
    await openDetail({ formula_id: f.formula_id })
    await loadFormulaList()
  } catch (e) {
    message.error(MESSAGES.saveFailed + '，请检查网络或联系管理员')
  } finally {
    savingBom.value = false
  }
}

// 通用行 key：基于记录内容的稳定哈希
const contentRowKey = (r) => {
  if (!r) return Math.random().toString(36).slice(2)
  if (r.material_id) return r.material_id
  if (r.name) return r.name
  if (r.equipment) return r.equipment
  return JSON.stringify(r).slice(0, 64)
}

function formatTime(t) {
  if (!t) return '—'
  // 兼容 ISO 字符串与已格式化字符串
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ── 配方列表 ──
const formulaList = ref([])
const formulaListLoading = ref(false)
const filterSource = ref('')
const filterTarget = ref('')
const filterProjectId = ref('')

// 项目选项（来自全局项目上下文）
const projectOptions = computed(() =>
  (projectCtx.projectList || []).map((p) => ({
    label: p.name || p.project_id,
    value: p.project_id,
  })),
)

// 候选 BOM 的 project_id 反查表：candidate_id → project_id
const candidateProjectMap = ref({})

// 前端筛选：来源 + 目标材料 + 项目
const filteredFormulaList = computed(() => {
  let list = formulaList.value
  // 来源筛选
  if (filterSource.value === 'candidate_bom') {
    list = list.filter((f) => f.source === 'candidate_bom')
  } else if (filterSource.value === 'formula') {
    list = list.filter((f) => f.source !== 'candidate_bom')
  }
  // 目标材料筛选
  const t = (filterTarget.value || '').trim().toLowerCase()
  if (t) {
    list = list.filter((f) => (f.target_material || '').toLowerCase().includes(t))
  }
  // 项目筛选：候选 BOM 用 project_id 字段；配方设计版本无项目关联，项目筛选时隐藏
  if (filterProjectId.value) {
    list = list.filter((f) => {
      if (f.source === 'candidate_bom') {
        return (f.project_id || candidateProjectMap.value[f.candidate_id] || '') === filterProjectId.value
      }
      return false
    })
  }
  // 排序：候选 BOM 优先（避免被埋没在分页末尾），同来源按创建时间倒序
  const sourceWeight = (s) => (s === 'candidate_bom' ? 0 : 1)
  return [...list].sort((a, b) => {
    const sw = sourceWeight(a.source) - sourceWeight(b.source)
    if (sw !== 0) return sw
    const ta = new Date(a.created_at).getTime() || 0
    const tb = new Date(b.created_at).getTime() || 0
    return tb - ta
  })
})

function onFilterChange() {
  // 计算属性自动响应，无需额外操作
}

function resetFilter() {
  filterSource.value = ''
  filterTarget.value = ''
  filterProjectId.value = ''
}

// 切换项目时不自动筛选，由用户手动选择项目筛选

const formulaListColumns = computed(() => [
  { title: '配方编号', key: 'formula_id', width: 160 },
  { title: '来源', key: 'source', width: 110, align: 'center' },
  { title: '目标材料', dataIndex: 'target_material', key: 'target_material', ellipsis: true },
  { title: '版本', key: 'version', width: 80, align: 'center' },
  { title: '物料数', key: 'bom_count', width: 90, align: 'center' },
  { title: `总成本 (¥/${massUnit.value})`, key: 'total_cost_per_kg', width: 120, align: 'right' },
  { title: '更新时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'actions', width: 140, fixed: 'right' },
])

function onRowClick(record) {
  return {
    onClick: () => openDetail(record),
    style: { cursor: 'pointer' },
  }
}

async function loadFormulaList() {
  formulaListLoading.value = true
  try {
    const res = await listFormulas()
    formulaList.value = res.formulas || []
    // 构建候选 BOM 的 project_id 反查表
    await buildCandidateProjectMap()
  } catch {
    formulaList.value = []
  } finally {
    formulaListLoading.value = false
  }
}

// 构建候选 BOM 的 candidate_id → project_id 反查表
// 优先使用后端 /formulas 返回的 project_id 字段（0727 后端已回填）
async function buildCandidateProjectMap() {
  const map = {}
  for (const f of formulaList.value) {
    if (f.source === 'candidate_bom' && f.candidate_id && f.project_id) {
      map[f.candidate_id] = f.project_id
    }
  }
  candidateProjectMap.value = map
}

// ── 配方详情抽屉 ──
const detailVisible = ref(false)
const detailLoading = ref(false)
const currentFormula = ref(null)
const formulaDetailTab = ref('bom') // 配方详情当前选中的tab

async function openDetail(formula) {
  detailVisible.value = true
  detailLoading.value = true
  // 切换配方时重置编辑状态机，确保默认只读
  isEditing.value = false
  _editSnapshot = null
  try {
    const res = await getFormula(formula.formula_id)
    currentFormula.value = res
    currentFormulaId.value = res.formula_id
  } catch {
    currentFormula.value = null
  } finally {
    detailLoading.value = false
  }
}

// ── 生成新配方抽屉 ──
const designVisible = ref(false)
const target = ref('')
const quantity = ref(1)
const quantityPreset = ref(undefined)
const loading = ref(false)
const result = ref(null)
const currentFormulaId = ref('')
const currentScenarioId = ref('')

const targetOptions = ref([])

const batchPresets = computed(() => [
  { label: `实验室级 1 ${massUnit.value}`, value: 1 },
  { label: `小试 10 ${massUnit.value}`, value: 10 },
  { label: `中试 100 ${massUnit.value}`, value: 100 },
  { label: `量产 1000 ${massUnit.value}`, value: 1000 },
])

function filterOption(input, option) {
  return (option.label || '').toLowerCase().includes(input.toLowerCase())
}

function onPresetChange(val) {
  if (val != null) quantity.value = val
}

function openDesignDrawer() {
  designVisible.value = true
}

async function onDesign() {
  if (!target.value || (typeof target.value === 'string' && !target.value.trim())) {
    message.warning('请选择或输入目标材料')
    return
  }
  loading.value = true
  try {
    const targetArg = { candidate: target.value, target_property: 'ionic_conductivity' }
    result.value = await client.post('/mcp/tools/design_formula/call', {
      arguments: { target_material: targetArg, quantity_kg: quantity.value },
    }, { timeout: 30000 })
    if (result.value?.error) {
      message.error(`配方生成失败：${result.value.error}`)
      result.value = null
    }
  } catch (e) {
    message.error(`配方生成失败：${e?.response?.data?.detail || e?.message || '服务异常，请稍后重试'}`)
    result.value = null
  } finally {
    loading.value = false
  }
}

// ── 保存配方版本 ──
const saveModalVisible = ref(false)
const saveSubmitting = ref(false)
const changeSummary = ref('')

function onSaveFormula() {
  // 生成抽屉：使用 result；详情抽屉：使用 currentFormula
  const hasResult = !!result.value
  const hasCurrent = !!currentFormula.value
  if (!hasResult && !hasCurrent) {
    message.warning('请先生成或选择配方')
    return
  }
  saveModalVisible.value = true
}

function onPrepareSample() {
  const formula = currentFormula.value
  if (!formula) return
  // 先关闭详情抽屉，避免跳转后抽屉遮挡样品管理页
  detailVisible.value = false
  router.push({
    path: '/samples',
    query: {
      formula_id: formula.formula_id,
      target: formula.target_material,
      scenario_id: currentScenarioId.value || undefined,
    },
  })
}

async function submitSaveFormula() {
  saveSubmitting.value = true
  try {
    // 优先使用生成结果，否则使用当前详情配方
    const source = result.value || {
      bom: currentFormula.value?.bom || [],
      bop: currentFormula.value?.bop || [],
      ehs: currentFormula.value?.ehs || {},
      material_cost: currentFormula.value?.material_cost || 0,
      process_cost: currentFormula.value?.process_cost || 0,
      total_cost_per_kg: currentFormula.value?.total_cost_per_kg || 0,
      process_cost_breakdown: currentFormula.value?.process_cost_breakdown || [],
    }
    const payload = {
      formula_id: currentFormulaId.value,
      target_material: target.value || currentFormula.value?.target_material || '',
      quantity_kg: quantity.value || currentFormula.value?.quantity_kg || 1,
      bom: source.bom || [],
      bop: source.bop || [],
      ehs: source.ehs || {},
      material_cost: source.material_cost || 0,
      process_cost: source.process_cost || 0,
      total_cost_per_kg: source.total_cost_per_kg || 0,
      process_cost_breakdown: source.process_cost_breakdown || [],
      change_summary: changeSummary.value || '保存配方版本',
      scenario_id: currentScenarioId.value || '',
    }
    const saved = await saveFormula(payload)
    currentFormulaId.value = saved.formula_id
    message.success(`已保存配方版本 ${saved.formula_id}-V${saved.version_number.toString().padStart(2, '0')}`)
    saveModalVisible.value = false
    designVisible.value = false
    result.value = null
    changeSummary.value = ''
    await loadFormulaList()
  } catch {
    /* 错误由拦截器统一处理 */
  } finally {
    saveSubmitting.value = false
  }
}

// ── 历史版本 ──
const historyModalVisible = ref(false)
const historyFormulaId = ref('')
const historyVersions = ref([])
const historyLoading = ref(false)

async function onViewHistory(formula) {
  historyFormulaId.value = formula.formula_id
  historyModalVisible.value = true
  historyLoading.value = true
  try {
    const res = await getFormulaHistory(formula.formula_id)
    historyVersions.value = res.versions || []
  } catch {
    historyVersions.value = []
  } finally {
    historyLoading.value = false
  }
}

async function onActivateVersion(version) {
  try {
    await activateFormulaVersion(version.formula_id, version.version_id)
    message.success('已切换为当前活跃版本')
    // 刷新历史列表
    if (historyModalVisible.value) {
      await onViewHistory(version)
    }
    await loadFormulaList()
    // 若详情抽屉打开，刷新详情
    if (detailVisible.value && currentFormula.value?.formula_id === version.formula_id) {
      await openDetail({ formula_id: version.formula_id })
    }
  } catch {
    /* 错误由拦截器统一处理 */
  }
}

// ── BOM/BOP/EHS 表格列定义（单位从 MDM 主数据获取）──
const bomColumns = computed(() => {
  const massUnit = unitSymbols.value.mass || 'kg'
  return [
    { title: '原料名称', dataIndex: 'material_name', key: 'name', ellipsis: true },
    { title: 'CAS号', dataIndex: 'cas_number', key: 'cas', width: 120 },
    { title: `用量 (${massUnit})`, dataIndex: 'amount_kg', key: 'amount', width: 100, align: 'right' },
    { title: `单价 (¥/${massUnit})`, dataIndex: 'unit_price', key: 'price', width: 110, align: 'right' },
    { title: '成本 (¥)', key: 'cost', width: 100, align: 'right' },
    { title: '供应商', dataIndex: 'supplier', key: 'supplier', ellipsis: true },
    { title: '库存', key: 'in_stock', width: 80, align: 'center' },
    { title: '操作', key: 'bom_op', width: 70, align: 'center' },
  ]
})

const bopColumns = computed(() => {
  const tempUnit = unitSymbols.value.temperature || '°C'
  const timeUnit = unitSymbols.value.time || 'h'
  return [
    { title: '工艺步骤', dataIndex: 'step', key: 'step', width: 100 },
    { title: '设备', dataIndex: 'equipment', key: 'equipment', ellipsis: true },
    { title: `温度 (${tempUnit})`, dataIndex: 'temperature', key: 'temp', width: 100, align: 'right' },
    { title: `时间 (${timeUnit})`, dataIndex: 'duration_h', key: 'duration', width: 90, align: 'right' },
    { title: '关键参数', dataIndex: 'key_params', key: 'params', ellipsis: true },
    { title: '操作', key: 'bop_op', width: 70, align: 'center' },
  ]
})

const costBreakdownColumns = computed(() => {
  const timeUnit = unitSymbols.value.time || 'h'
  return [
    { title: '工艺步骤', dataIndex: 'step', key: 'step' },
    { title: '设备', dataIndex: 'equipment', key: 'equipment', ellipsis: true },
    { title: `工时 (${timeUnit})`, dataIndex: 'duration_h', key: 'duration_h', align: 'right', className: 'tabular-nums' },
    { title: '设备折旧 (¥)', dataIndex: 'depreciation_cost', key: 'depreciation_cost', align: 'right', className: 'tabular-nums', customRender: ({ text }) => Number(text).toFixed(2) },
    { title: '能耗 (¥)', dataIndex: 'energy_cost', key: 'energy_cost', align: 'right', className: 'tabular-nums', customRender: ({ text }) => Number(text).toFixed(2) },
    { title: '人工 (¥)', dataIndex: 'labor_cost', key: 'labor_cost', align: 'right', className: 'tabular-nums', customRender: ({ text }) => Number(text).toFixed(2) },
    { title: '小计 (¥)', dataIndex: 'subtotal', key: 'subtotal', align: 'right', className: 'tabular-nums', customRender: ({ text }) => Number(text).toFixed(2) },
  ]
})

const hazardColumns = [
  { title: '物料', dataIndex: 'material_name', key: 'material_name', ellipsis: true },
  { title: 'REACH 核查', key: 'reach_status', width: 90, align: 'center' },
  { title: 'GHS 分类', dataIndex: 'ghs_classification', key: 'ghs_classification', ellipsis: true },
  { title: '闪点', dataIndex: 'flash_point', key: 'flash_point', ellipsis: true },
  { title: '反应性危害', dataIndex: 'reactivity_hazard', key: 'reactivity_hazard', ellipsis: true },
  { title: 'SDS', key: 'sds_link', width: 90, align: 'center' },
]

const historyColumns = computed(() => [
  { title: '版本', key: 'version', width: 80, align: 'center' },
  { title: '变更说明', dataIndex: 'change_summary', key: 'change_summary', ellipsis: true },
  { title: `总成本 (¥/${massUnit.value})`, key: 'total_cost_per_kg', width: 120, align: 'right' },
  { title: '操作人', dataIndex: 'created_by', key: 'created_by', width: 100 },
  { title: '时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'actions', width: 160 },
])

// ── 设备台账校验与快速登记 ──
const equipmentList = ref([])
const equipmentNames = computed(() => new Set(equipmentList.value.map(e => e.name)))

function isEquipmentValid(name) {
  if (!name) return true
  return equipmentNames.value.has(name)
}

const equipModalVisible = ref(false)
const equipSubmitting = ref(false)
const equipForm = ref({ name: '', model: '', responsible_person: '', location: '' })

function openEquipmentQuickRegister(name) {
  equipForm.value = { name, model: '', responsible_person: '', location: '' }
  equipModalVisible.value = true
}

async function submitEquipmentQuickRegister() {
  const form = equipForm.value
  if (!form.name?.trim()) {
    message.warning('设备名称不能为空')
    return
  }
  equipSubmitting.value = true
  try {
    await createEquipment({
      name: form.name.trim(),
      model: form.model?.trim() || '',
      responsible_person: form.responsible_person?.trim() || '',
      location: form.location?.trim() || '',
    })
    message.success(`设备「${form.name.trim()}」已登记入账`)
    equipModalVisible.value = false
    equipmentList.value = (await listEquipment()) || []
  } catch {
    /* 错误提示由拦截器统一处理 */
  } finally {
    equipSubmitting.value = false
  }
}

onMounted(async () => {
  // 初始化全局项目上下文（不默认启用项目筛选，避免列表为空）
  try {
    await projectCtx.fetchProjects()
  } catch {
    // ignore
  }

  // 加载 MDM 单位符号（用于列标题、表单标签等动态单位显示）
  try {
    await loadUnitSymbols()
  } catch {
    // ignore，回退到默认符号
  }

  // 加载物料库作为目标材料选项
  try {
    const data = await getRawMaterials()
    const materials = data.materials || []
    targetOptions.value = materials.map((m) => ({
      label: `${m.name} (${m.material_id})`,
      value: m.name,
    }))
  } catch {
    targetOptions.value = []
  }

  // 加载设备台账用于 BOP 设备校验
  try {
    equipmentList.value = (await listEquipment()) || []
  } catch {
    equipmentList.value = []
  }

  // 从路由 query 接收候选材料
  const {
    target: qTarget, formula, smiles, formula_id, scenario_id,
    candidate_id: qCandidateId, route_id: qRouteId, synthesis_task_id: qSynthTaskId,
  } = route.query
  if (scenario_id) {
    currentScenarioId.value = String(scenario_id)
  }
  if (qTarget) {
    target.value = String(qTarget)
  } else if (formula) {
    target.value = String(formula)
  } else if (smiles) {
    target.value = String(smiles)
  }

  // 加载配方列表
  await loadFormulaList()

  // 优先处理「从候选合成路径进入」：自动生成或打开对应 BOM 草案
  const hasRouteInfo = qCandidateId && qRouteId && qSynthTaskId
  if (hasRouteInfo) {
    const info = {
      candidate_id: String(qCandidateId),
      route_id: String(qRouteId),
      synthesis_task_id: String(qSynthTaskId),
      route_label: String(qRouteId),
    }
    routeBomInfo.value = info
    routeBomLoading.value = true
    try {
      // 1. 先查已有 BOM（避免重复生成）
      let existing = findExistingCandidateBom(info.candidate_id, info.route_id)
      // 2. 不存在则调用后端生成
      if (!existing) {
        await generateBomFromRoute(info)
        await loadFormulaList()
        existing = findExistingCandidateBom(info.candidate_id, info.route_id)
      }
      // 3. 打开详情
      if (existing) {
        await openDetail(existing)
      } else {
        message.warning('合成路径 BOM 生成失败，请稍后重试或在配方列表中手动查找')
      }
    } catch (e) {
      message.error('从合成路径生成 BOM 失败：' + (e?.message || '未知错误'))
    } finally {
      routeBomLoading.value = false
    }
    return // 已处理 route 流程，跳过默认的「打开生成抽屉」逻辑
  }

  // 若 URL 携带 formula_id，自动打开详情
  if (formula_id) {
    const matchedRow = formulaList.value.find((f) => f.formula_id === formula_id)
    if (matchedRow) {
      await openDetail(matchedRow)
    }
  }

  // 若 URL 携带 target，自动打开生成抽屉
  if (target.value) {
    openDesignDrawer()
  }
})
</script>

<style scoped>
/* 配方详情Tab样式 */
.formula-detail-tabs {
  margin-bottom: 16px;
}

.formula-detail-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 12px;
}

.design-agent-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}

.design-agent-label {
  font-size: 12px;
  color: var(--text-muted);
}
.formula-design-page {
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

.list-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}

.filter-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px 12px 12px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}

.filter-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.filter-stats {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-muted);
}

.formula-table :deep(.ant-table-row:hover) {
  cursor: pointer;
}

.formula-id-text {
  font-weight: 600;
  color: var(--text-primary);
}

.text-muted {
  color: var(--text-muted, #94a3b8);
  font-size: 12px;
}

/* 详情抽屉内部分块 */
.detail-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-light, #f0f0f0);
}

.head-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.head-sub {
  font-size: 13px;
  color: var(--text-secondary, #666);
  line-height: 1.6;
}

.head-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-end;
}

.cost-row {
  margin-bottom: 4px;
}

.kpi-card {
  background: var(--light-bg-hover, #fafafa);
}

.section-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  padding-left: 8px;
  border-left: 3px solid var(--primary);
}

.cost-model-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
  line-height: 1.5;
}

.cost-breakdown-collapse :deep(.ant-collapse-header) {
  font-size: 13px;
  color: var(--text-secondary, #475569);
}

.design-actions {
  padding-top: 12px;
  border-top: 1px solid var(--border-light, #f0f0f0);
  display: flex;
  justify-content: flex-end;
}
</style>
