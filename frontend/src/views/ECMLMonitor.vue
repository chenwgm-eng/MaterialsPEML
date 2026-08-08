<template>
  <div class="ecml-monitor">
    <div class="page-header ecml-header">
      <div class="header-text">
        <div class="title-row">
          <h1 class="page-title">实验闭环迭代</h1>
        </div>
        <p class="page-subtitle">7 步闭环：路由 → 生成 → 工业化验证 → 预测 → 验证 → 实验 → 反馈</p>
        <p class="page-usage-hint">使用说明：仅在已有至少 1 轮实验数据时可用；完成后得到下一轮推荐候选材料与参数调整建议</p>
      </div>
      <router-link to="/ecml/runs" custom v-slot="{ navigate, href }">
        <a class="ant-btn" :href="href" @click.prevent="navigate">
          <HistoryOutlined /> 运行历史
        </a>
      </router-link>
    </div>

    <!-- P3-2：研发工作台派生上下文横幅 -->
    <ResearchContextBanner />

    <!-- 前置条件检查横幅：实验数据不足时提示并禁用运行 -->
    <a-alert
      v-if="!prerequisitesMet"
      type="warning"
      show-icon
      banner
      class="prerequisite-banner"
    >
      <template #message>
        <span>前置条件未满足：</span>
        <a-tag color="orange">{{ prerequisiteMessage }}</a-tag>
      </template>
      <template #description>
        {{ prerequisiteDetail }}
      </template>
    </a-alert>

    <!-- Control Panel -->
    <ECMLControlPanel
      :form="form"
      :property-options="propertyOptions"
      :running="ecmlStore.running"
      :cancelled="cancelled"
      :prerequisites-met="prerequisitesMet"
      :multi-objective-options="multiObjectiveOptions"
      :multi-objective-config="multiObjectiveConfig"
      :hide-objective-weights="hideObjectiveWeights"
      @run="onRun"
      @cancel="onCancel"
      @run-again="onRunAgain"
    />

    <!-- 贝叶斯优化决策引擎：策略配置 + 训练池统计 + 运行态可视化 + 复核下发 -->
    <ECMLStrategyPanel
      :run-id="currentRunId"
      :target="form.target"
      :target-property="form.target_property"
      :pool-stats="boRound?.pool"
      @start="onStrategyStart"
      @acquisition-change="(v) => (currentAcquisition = v)"
    />

    <ECMLRoundResult
      :round="boRound"
      :current-scenario-id="currentScenarioId"
      @confirmed="onRoundConfirmed"
    />

    <!-- 失败状态提示 -->
    <a-alert
      v-if="error"
      type="error"
      :message="error"
      show-icon
      closable
      style="margin-bottom: 12px"
    >
      <template #action>
        <a-button size="small" type="primary" @click="onRetry">重试</a-button>
      </template>
    </a-alert>

    <!-- Step Flow -->
    <a-card class="flow-card" :bordered="false" v-if="ecmlStore.state">
      <template #title>
        <div class="flow-title">
          <span>执行状态</span>
          <a-space>
            <a-tag v-if="cancelled" color="orange">已取消</a-tag>
            <template v-else-if="ecmlStore.state?.is_complete">
              <a-tag color="green">已完成</a-tag>
              <a-button size="small" type="primary" @click="onRunAgain">再次运行</a-button>
            </template>
            <a-tag v-else-if="runStatus === 'timeout'" color="red">运行超时</a-tag>
            <a-tag v-else-if="runStatus === 'failed'" color="red">运行失败</a-tag>
            <a-tag v-else color="processing">运行中</a-tag>
            <a-button v-if="ecmlStore.running" size="small" @click="showIntermediate = true">
              查看中间结果
            </a-button>
          </a-space>
        </div>
      </template>
      <!-- 进度信息 -->
      <div v-if="ecmlStore.running || runStatus === 'running'" class="progress-info">
        <a-spin size="small" />
        <span class="current-step">
          运行中... 已等待 {{ formatElapsed(elapsed) }}
        </span>
        <span class="elapsed-time">
          {{ currentStepLabel }} · 第 {{ pollingCount }}/{{ MAX_POLLING }} 次轮询
        </span>
      </div>
      <a-alert
        v-else-if="runStatus === 'timeout'"
        type="warning"
        message="运行超时"
        description="后端可能仍在运行，请稍后在迭代历史中查看结果"
        show-icon
        style="margin-bottom: 12px"
      />
      <a-alert
        v-else-if="runStatus === 'failed'"
        type="error"
        message="运行失败"
        show-icon
        style="margin-bottom: 12px"
      />
      <ECMLStepFlow
        :current-step="currentStep"
        :completed-steps="completedSteps"
        :failed-steps="failedSteps"
        :no-result="noResult"
        :clickable-steps="clickableSteps"
        @step-click="onStepClick"
      />
    </a-card>

    <!-- Committee Gate + DFT Queue（由子组件内部 watch 拉取） -->
    <ECMLCommitteePanel
      :run-id="currentRunId"
      :blocked-reason="ecmlStore.state?.blocked_reason || ''"
    />

    <!-- 结果概览：回答用户最关心的"找到了什么、哪个最好、下一步做什么" -->
    <ECMLResultOverview
      ref="resultOverviewRef"
      :state="ecmlStore.state"
      :candidates="detailCandidates"
      :synthesizable="detailSynthesizable"
      :verified="detailVerified"
      :experiments="detailExperiments"
      :fallback-target="form.target"
      :fallback-property="form.target_property"
      :property-options="propertyOptions"
      :cond-unit="condUnit"
      :energy-unit="energyUnit"
      :energy-per-atom-unit="energyPerAtomUnit"
      @send-best-to-experiment="sendBestToExperiment"
      @send-best-to-formula="sendBestToFormula"
      @scroll-to-detail="scrollToDetail"
    />

    <!-- 候选材料详情 -->
    <a-card id="ecml-detail-candidates" class="detail-card" :bordered="false" v-if="detailCandidates.length || ecmlStore.state?.is_complete" title="候选材料">
      <EmptyState v-if="!detailCandidates.length" type="data" description="本轮迭代未生成候选材料" />
      <template v-else>
      <a-tabs v-if="hasMultiObjective" size="small" class="chart-tabs">
        <a-tab-pane key="pareto" tab="帕累托前沿">
          <ParetoChart :candidates="candidatesWithObjectives" @select="onChartSelect" />
        </a-tab-pane>
        <a-tab-pane key="radar" tab="雷达图">
          <RadarChart :candidates="candidatesWithObjectives" />
        </a-tab-pane>
      </a-tabs>
      <a-table
        :columns="candidateColumns"
        :data-source="detailCandidates"
        :row-key="candidateRowKey"
        :pagination="{ pageSize: 10 }"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'molecule'">
            <MoleculeView :smiles="record.smiles || record.psmiles" :size="120" />
          </template>
          <template v-else-if="column.key === 'source'">
            <a-tag v-if="record.source" :color="getSourceBadge(record).color">{{ getSourceBadge(record).label }}</a-tag>
            <span v-else class="text-muted">-</span>
          </template>
          <template v-else-if="column.key === 'provenance'">
            <a-tag
              v-if="record.provenance"
              :color="evidenceLevelColor(record.provenance.evidence_level)"
              class="provenance-badge"
              @click.stop="showAudit(record.provenance)"
            >
              {{ provenanceLabel(record.provenance) }}
            </a-tag>
            <span v-else class="text-muted">-</span>
          </template>
          <template v-else-if="column.key === 'industrial'">
            <a-tooltip v-if="record.reject_reasons && (Array.isArray(record.reject_reasons) ? record.reject_reasons.length : true)" :title="rejectReasonText(record.reject_reasons)">
              <a-tag color="red">工业化淘汰</a-tag>
            </a-tooltip>
            <a-tooltip v-else-if="record.industrialization_error" :title="record.industrialization_error">
              <a-tag color="orange">工业化异常</a-tag>
            </a-tooltip>
            <a-tag v-else-if="record.industrial_recipe" color="green">工业化通过</a-tag>
            <span v-else class="text-muted">-</span>
          </template>
          <template v-else-if="column.key === 'mo_status'">
            <span class="mo-status-tags">
              <a-tag
                v-for="obj in moObjectivesForTable"
                :key="obj.key"
                :color="getMoStatus(record, obj) ? 'green' : 'red'"
                class="mo-status-tag"
              >
                {{ obj.name }} {{ getMoStatus(record, obj) ? '达标' : '不达标' }}
              </a-tag>
            </span>
          </template>
        </template>
      </a-table>
      </template>
    </a-card>

    <!-- 实验分析简报（QC 通过后由 ExperimentAnalystAgent 生成） -->
    <a-card class="detail-card" :bordered="false" v-if="ecmlAnalysisBrief?.analysis" title="📊 分析简报">
      <a-alert :message="ecmlAnalysisBrief.analysis?.summary" type="info" show-icon style="margin-bottom: 12px" />
      <a-row v-if="ecmlAnalysisBrief.analysis?.statistics" :gutter="16">
        <a-col :xs="12" :sm="6">
          <a-card size="small" class="stat-card">
            <a-statistic title="均值" :value="ecmlAnalysisBrief.analysis.statistics.mean" :precision="4" />
          </a-card>
        </a-col>
        <a-col :xs="12" :sm="6">
          <a-card size="small" class="stat-card">
            <a-statistic title="标准差" :value="ecmlAnalysisBrief.analysis.statistics.std" :precision="4" />
          </a-card>
        </a-col>
        <a-col :xs="12" :sm="6">
          <a-card size="small" class="stat-card">
            <a-statistic title="样本数" :value="ecmlAnalysisBrief.analysis.statistics.sample_count" />
          </a-card>
        </a-col>
        <a-col :xs="12" :sm="6">
          <a-card size="small" class="stat-card">
            <div class="stat-label">趋势</div>
            <a-tag :color="trendColor(ecmlAnalysisBrief.analysis.statistics.trend)">
              {{ ecmlAnalysisBrief.analysis.statistics.trend }}
            </a-tag>
          </a-card>
        </a-col>
      </a-row>
      <a-row :gutter="16" style="margin-top: 8px">
        <a-col :sm="12" v-if="ecmlAnalysisBrief.analysis?.anomalies?.length">
          <div class="analysis-subtitle">异常点（{{ ecmlAnalysisBrief.analysis.anomalies.length }}）</div>
          <a-list :data-source="ecmlAnalysisBrief.analysis.anomalies" size="small" :split="false" bordered>
            <template #renderItem="{ item }">
              <a-list-item>
                <a-tag color="red">{{ item.result_id }}</a-tag>
                <span class="text-muted">值 {{ item.value }}，{{ item.reason }}</span>
              </a-list-item>
            </template>
          </a-list>
        </a-col>
        <a-col :sm="12" v-if="ecmlAnalysisBrief.analysis?.recommendations?.length">
          <div class="analysis-subtitle">建议</div>
          <a-list :data-source="ecmlAnalysisBrief.analysis.recommendations" size="small" :split="false" bordered>
            <template #renderItem="{ item }">
              <a-list-item>{{ item }}</a-list-item>
            </template>
          </a-list>
        </a-col>
      </a-row>
    </a-card>

    <!-- 工业化验证结果 -->
    <a-card id="ecml-detail-synthesizable" class="detail-card" :bordered="false" v-if="detailSynthesizable.length || ecmlStore.state?.is_complete" title="工业化验证">
      <EmptyState v-if="!detailSynthesizable.length" type="data" description="本轮迭代无工业化验证结果" />
      <a-table
        v-else
        :columns="synthesizableColumns"
        :data-source="detailSynthesizable"
        :row-key="synthesizableRowKey"
        :expandable="synthesizableExpandable"
        :pagination="{ pageSize: 10 }"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'matched'">
            {{ matchedMaterialsText(record) }}
          </template>
          <template v-else-if="column.key === 'cost'">
            {{ formatCost(record.estimated_cost) }}
          </template>
          <template v-else-if="column.key === 'score'">
            {{ formatScore(record.industrialization_score) }}
          </template>
        </template>
        <template #expandedRowRender="{ record }">
          <div class="recipe-detail">
            <div v-if="record.industrial_recipe?.bom?.length" class="recipe-block">
              <div class="recipe-subtitle">BOM 物料清单</div>
              <a-table
                :columns="columnsFromData(record.industrial_recipe.bom)"
                :data-source="record.industrial_recipe.bom"
                :pagination="false"
                size="small"
              />
            </div>
            <div v-if="record.industrial_recipe?.bop?.length" class="recipe-block">
              <div class="recipe-subtitle">BOP 工艺步骤</div>
              <a-table
                :columns="columnsFromData(record.industrial_recipe.bop)"
                :data-source="record.industrial_recipe.bop"
                :pagination="false"
                size="small"
              />
            </div>
          </div>
        </template>
      </a-table>
    </a-card>

    <!-- 性质预测结果 -->
    <a-card id="ecml-detail-predictions" class="detail-card" :bordered="false" v-if="detailPredictions.length" title="性质预测">
      <a-table
        :columns="predictionColumns"
        :data-source="detailPredictions"
        :row-key="predictionRowKey"
        :pagination="{ pageSize: 10 }"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'molecule'">
            <MoleculeView :smiles="record.smiles || record.psmiles" :size="120" />
          </template>
          <template v-else-if="column.key === 'material'">
            {{ materialLabel(record) }}
          </template>
          <template v-else-if="column.key === 'value'">
            {{ formatValueUnit(record.value, record.unit) }}
          </template>
          <template v-else-if="column.key === 'provenance_badge'">
            <a-tag
              v-if="record.provenance"
              :color="evidenceLevelColor(record.provenance.evidence_level)"
              class="provenance-badge"
              @click.stop="showAudit(record.provenance)"
            >
              {{ provenanceLabel(record.provenance) }}
            </a-tag>
            <span v-else class="text-muted">-</span>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- DFT 验证结果 -->
    <a-card id="ecml-detail-verified" class="detail-card" :bordered="false" v-if="detailVerified.length" title="DFT 验证">
      <template #extra>
        <a-space>
          <a-button size="small" @click="sendVerifiedToExperiment">发送到实验</a-button>
          <a-button size="small" @click="sendVerifiedToFormula">发送到配方</a-button>
        </a-space>
      </template>
      <a-table
        :columns="verifiedColumns"
        :data-source="detailVerified"
        :row-key="verifiedRowKey"
        :pagination="{ pageSize: 10 }"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'material'">
            {{ materialLabel(record) }}
          </template>
          <template v-else-if="column.key === 'vvalue'">
            {{ formatValueUnit(record.verification_value, record.unit) }}
          </template>
          <template v-else-if="column.key === 'converged'">
            <a-tag :color="record.verification_converged ? 'green' : 'red'">
              {{ record.verification_converged ? '收敛' : '未收敛' }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'provenance_badge'">
            <a-tag
              v-if="record.provenance"
              :color="evidenceLevelColor(record.provenance.evidence_level)"
              class="provenance-badge"
              @click.stop="showAudit(record.provenance)"
            >
              {{ provenanceLabel(record.provenance) }}
            </a-tag>
            <span v-else class="text-muted">-</span>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- DFT Queue 已合并到 ECMLCommitteePanel 子组件 -->

    <!-- 实验结果 -->
    <a-card id="ecml-detail-experiments" class="detail-card" :bordered="false" v-if="detailExperiments.length" title="实验结果">
      <a-table
        :columns="experimentColumns"
        :data-source="detailExperiments"
        :row-key="experimentRowKey"
        :pagination="{ pageSize: 10 }"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'value'">
            {{ formatValueUnit(record.value, record.unit) }}
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.status === 'success' ? 'green' : (record.status === 'failed' ? 'red' : 'blue')">
              {{ record.status || '-' }}
            </a-tag>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 反馈与建议 -->
    <a-card id="ecml-detail-feedback" class="detail-card" :bordered="false" v-if="detailFeedback" title="反馈与建议">
      <a-descriptions v-if="detailFeedback.summary" :column="1" size="small" class="feedback-block">
        <a-descriptions-item label="总结">{{ detailFeedback.summary }}</a-descriptions-item>
      </a-descriptions>
      <div v-if="Array.isArray(detailFeedback.recommendations) && detailFeedback.recommendations.length" class="feedback-block">
        <div class="recipe-subtitle">建议</div>
        <a-list :data-source="detailFeedback.recommendations" size="small" :split="false">
          <template #renderItem="{ item }">
            <a-list-item>{{ item }}</a-list-item>
          </template>
        </a-list>
      </div>
      <a-descriptions
        v-if="detailFeedback.next_iteration_params && Object.keys(detailFeedback.next_iteration_params).length"
        :column="2"
        size="small"
        bordered
        class="feedback-block"
        title="下一轮推荐参数"
      >
        <a-descriptions-item v-for="(val, key) in detailFeedback.next_iteration_params" :key="key" :label="String(key)">
          {{ val }}
        </a-descriptions-item>
      </a-descriptions>
      <!-- 下一步操作指引：根据当前状态提供明确跳转入口 -->
      <div class="feedback-next-actions">
        <div class="feedback-next-title">下一步操作</div>
        <a-space wrap>
          <a-button v-if="ecmlStore.state?.is_complete" size="small" type="primary" @click="scrollToResultOverview">
            查看推荐候选并发送到实验/配方
          </a-button>
          <a-button v-if="ecmlStore.state?.is_complete" size="small" @click="restartECML">
            应用推荐参数重新迭代
          </a-button>
          <a-button v-if="ecmlStore.state?.blocked_reason" size="small" type="primary" danger @click="goToCommitteeApproval">
            前往委员会审批（当前被阻断）
          </a-button>
        </a-space>
      </div>
    </a-card>

    <!-- 迭代历史 -->
    <a-card class="detail-card" :bordered="false" v-if="iterationHistory.length > 0" title="迭代历史">
      <a-table
        :data-source="iterationHistory"
        :columns="iterationHistoryColumns"
        :pagination="{ pageSize: 5 }"
        size="small"
        row-key="run_id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'iteration_id'">
            <a-tag color="blue">第 {{ record.iteration_id }} 轮</a-tag>
          </template>
          <template v-else-if="column.key === 'updated_at'">
            {{ record.updated_at ? new Date(record.updated_at).toLocaleString() : '-' }}
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag v-if="record.status === 'timeout'" color="red">超时</a-tag>
            <a-tag v-else-if="record.is_complete" color="green">已完成</a-tag>
            <a-tag v-else color="processing">进行中</a-tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <a-button type="link" size="small" @click="viewIteration(record)">查看详情</a-button>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 下一轮候选建议 -->
    <a-card
      class="detail-card"
      :bordered="false"
      v-if="nextRoundSuggestions && (nextRoundSuggestions.next_candidates?.length || nextRoundSuggestions.reasoning)"
      title="下一轮候选建议"
    >
      <template #extra>
        <a-button type="primary" size="small" :loading="startingNextRound" @click="onStartNextRound">
          一键启动下一轮
        </a-button>
      </template>
      <a-alert
        v-if="nextRoundSuggestions?.reasoning"
        :message="nextRoundSuggestions.reasoning"
        type="info"
        show-icon
        style="margin-bottom: 12px"
      />
      <!-- P1-1：批量质量告警（模型推理失效） -->
      <a-alert
        v-if="nextRoundSuggestions?.batch_quality_warning"
        :message="nextRoundSuggestions.batch_quality_warning"
        type="error"
        show-icon
        style="margin-bottom: 12px"
      />
      <!-- P1-1：被拦截的非法候选提示 -->
      <a-alert
        v-if="nextRoundSuggestions?.blocked_candidates?.length"
        :message="`已拦截 ${nextRoundSuggestions.blocked_candidates.length} 个未通过化学式合法性校验的候选材料：${nextRoundSuggestions.blocked_candidates.map(c => c.name).join('、')}`"
        type="warning"
        show-icon
        style="margin-bottom: 12px"
      />
      <EmptyState v-if="!nextRoundSuggestions.next_candidates?.length" type="data" description="暂无下一轮候选建议" />
      <a-table
        v-else
        :data-source="nextRoundSuggestions.next_candidates"
        :columns="nextRoundColumns"
        :pagination="false"
        size="small"
        :row-key="(r) => r.name"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'strategy'">
            <a-tag :color="record.strategy === 'exploitation' ? 'green' : 'orange'">
              {{ record.strategy === 'exploitation' ? '利用型' : '探索型' }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'data_quality'">
            <a-tooltip v-if="record.data_quality_flag === 'invalid'" :title="(record.quality_issues || []).join('；')">
              <a-tag color="red">⚠ 数据异常</a-tag>
            </a-tooltip>
            <a-tag v-else color="green">正常</a-tag>
          </template>
          <template v-else-if="column.key === 'expected_performance'">
            {{ record.expected_performance != null ? Number(record.expected_performance).toFixed(4) : '-' }}
          </template>
          <template v-else-if="column.key === 'identifier'">
            {{ record.smiles || record.psmiles || record.formula || '-' }}
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 中间结果 Drawer -->
    <a-drawer
      :open="showIntermediate"
      title="中间结果"
      placement="right"
      width="900px"
      :footer="null"
      :destroy-on-close="true"
      @update:open="(v) => (showIntermediate = v)"
    >
      <a-collapse v-if="ecmlStore.state" accordion>
        <a-collapse-panel v-if="detailCandidates.length" key="candidates" :header="`候选材料 (${detailCandidates.length})`">
          <a-table :columns="candidateColumns" :data-source="detailCandidates" :row-key="candidateRowKey" :pagination="false" size="small">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'molecule'">
                <MoleculeView :smiles="record.smiles || record.psmiles" :size="120" />
              </template>
              <template v-else-if="column.key === 'industrial'">
                <a-tooltip v-if="record.reject_reasons && (Array.isArray(record.reject_reasons) ? record.reject_reasons.length : true)" :title="rejectReasonText(record.reject_reasons)">
                  <a-tag color="red">工业化淘汰</a-tag>
                </a-tooltip>
                <a-tooltip v-else-if="record.industrialization_error" :title="record.industrialization_error">
                  <a-tag color="orange">工业化异常</a-tag>
                </a-tooltip>
                <a-tag v-else-if="record.industrial_recipe" color="green">工业化通过</a-tag>
                <span v-else class="text-muted">-</span>
              </template>
            </template>
          </a-table>
        </a-collapse-panel>
        <a-collapse-panel v-if="detailSynthesizable.length" key="synthesizable" :header="`工业化验证 (${detailSynthesizable.length})`">
          <a-table :columns="synthesizableColumns" :data-source="detailSynthesizable" :row-key="synthesizableRowKey" :expandable="synthesizableExpandable" :pagination="false" size="small">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'matched'">
                {{ matchedMaterialsText(record) }}
              </template>
              <template v-else-if="column.key === 'cost'">
                {{ formatCost(record.estimated_cost) }}
              </template>
              <template v-else-if="column.key === 'score'">
                {{ formatScore(record.industrialization_score) }}
              </template>
            </template>
            <template #expandedRowRender="{ record }">
              <div class="recipe-detail">
                <div v-if="record.industrial_recipe?.bom?.length" class="recipe-block">
                  <div class="recipe-subtitle">BOM 物料清单</div>
                  <a-table :columns="columnsFromData(record.industrial_recipe.bom)" :data-source="record.industrial_recipe.bom" :pagination="false" size="small" />
                </div>
                <div v-if="record.industrial_recipe?.bop?.length" class="recipe-block">
                  <div class="recipe-subtitle">BOP 工艺步骤</div>
                  <a-table :columns="columnsFromData(record.industrial_recipe.bop)" :data-source="record.industrial_recipe.bop" :pagination="false" size="small" />
                </div>
              </div>
            </template>
          </a-table>
        </a-collapse-panel>
        <a-collapse-panel v-if="detailPredictions.length" key="predictions" :header="`性质预测 (${detailPredictions.length})`">
          <a-table :columns="predictionColumns" :data-source="detailPredictions" :row-key="predictionRowKey" :pagination="false" size="small">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'molecule'">
                <MoleculeView :smiles="record.smiles || record.psmiles" :size="120" />
              </template>
              <template v-else-if="column.key === 'material'">
                {{ materialLabel(record) }}
              </template>
              <template v-else-if="column.key === 'value'">
                {{ formatValueUnit(record.value, record.unit) }}
              </template>
            </template>
          </a-table>
        </a-collapse-panel>
        <a-collapse-panel v-if="detailVerified.length" key="verified" :header="`DFT 验证 (${detailVerified.length})`">
          <a-table :columns="verifiedColumns" :data-source="detailVerified" :row-key="verifiedRowKey" :pagination="false" size="small">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'material'">
                {{ materialLabel(record) }}
              </template>
              <template v-else-if="column.key === 'vvalue'">
                {{ formatValueUnit(record.verification_value, record.unit) }}
              </template>
              <template v-else-if="column.key === 'converged'">
                <a-tag :color="record.verification_converged ? 'green' : 'red'">
                  {{ record.verification_converged ? '收敛' : '未收敛' }}
                </a-tag>
              </template>
            </template>
          </a-table>
        </a-collapse-panel>
        <a-collapse-panel v-if="detailExperiments.length" key="experiments" :header="`实验结果 (${detailExperiments.length})`">
          <a-table :columns="experimentColumns" :data-source="detailExperiments" :row-key="experimentRowKey" :pagination="false" size="small">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'value'">
                {{ formatValueUnit(record.value, record.unit) }}
              </template>
              <template v-else-if="column.key === 'status'">
                <a-tag :color="record.status === 'success' ? 'green' : (record.status === 'failed' ? 'red' : 'blue')">
                  {{ record.status || '-' }}
                </a-tag>
              </template>
            </template>
          </a-table>
        </a-collapse-panel>
        <a-collapse-panel v-if="detailFeedback" key="feedback" header="反馈与建议">
          <a-descriptions v-if="detailFeedback.summary" :column="1" size="small" class="feedback-block">
            <a-descriptions-item label="总结">{{ detailFeedback.summary }}</a-descriptions-item>
          </a-descriptions>
          <div v-if="Array.isArray(detailFeedback.recommendations) && detailFeedback.recommendations.length" class="feedback-block">
            <div class="recipe-subtitle">建议</div>
            <a-list :data-source="detailFeedback.recommendations" size="small" :split="false">
              <template #renderItem="{ item }">
                <a-list-item>{{ item }}</a-list-item>
              </template>
            </a-list>
          </div>
        </a-collapse-panel>
      </a-collapse>
      <EmptyState v-else type="data" description="暂无中间结果" />
    </a-drawer>

    <!-- 审计详情 Drawer -->
    <a-drawer
      :open="showAuditModal"
      title="证据审计详情"
      placement="right"
      width="600px"
      :footer="null"
      :destroy-on-close="true"
      @update:open="(v) => (showAuditModal = v)"
    >
      <a-descriptions v-if="auditSummary" :column="1" size="small" bordered>
        <a-descriptions-item label="来源">
          {{ auditSummary.source || '-' }}
        </a-descriptions-item>
        <a-descriptions-item label="证据等级">
          <a-tag :color="evidenceLevelColor(auditSummary.evidence_level)">
            {{ evidenceLevelLabel(auditSummary.evidence_level) }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="调用 ID">
          {{ auditSummary.invocation_id || '-' }}
        </a-descriptions-item>
        <a-descriptions-item label="时间">
          {{ auditSummary.timestamp || '-' }}
        </a-descriptions-item>
        <a-descriptions-item v-if="auditSummary.model" label="模型">
          {{ auditSummary.model }}
        </a-descriptions-item>
        <a-descriptions-item v-if="auditSummary.tool" label="工具">
          {{ auditSummary.tool }}
        </a-descriptions-item>
      </a-descriptions>
      <EmptyState v-else type="data" description="暂无审计详情" />
    </a-drawer>

    <!-- 步骤详情抽屉：点击流程节点展示该步骤的活动情况 -->
    <a-drawer
      :open="stepDetailVisible"
      :title="stepDetailTitle"
      placement="right"
      width="560px"
      :footer="null"
      :destroy-on-close="true"
      @update:open="(v) => (stepDetailVisible = v)"
    >
      <div v-if="stepDetailKey" class="step-detail-body">
        <!-- 步骤说明 -->
        <a-descriptions :column="1" size="small" bordered class="step-detail-desc">
          <a-descriptions-item label="状态">
            <a-tag v-if="failedSteps.includes(stepDetailKey)" color="red">失败/需干预</a-tag>
            <a-tag v-else-if="currentStep === stepDetailKey" color="processing">进行中</a-tag>
            <a-tag v-else-if="completedSteps.includes(stepDetailKey)" color="green">已完成</a-tag>
            <a-tag v-else>未开始</a-tag>
          </a-descriptions-item>
          <a-descriptions-item v-if="ecmlStore.state?.blocked_reason && currentStep === stepDetailKey" label="阻断原因">
            <span class="step-blocked-reason">{{ ecmlStore.state.blocked_reason }}</span>
          </a-descriptions-item>
        </a-descriptions>

        <!-- 输出产物 -->
        <div v-if="stepDetailOutputs.length" class="step-detail-section">
          <div class="step-detail-section-title">输出产物</div>
          <a-list :data-source="stepDetailOutputs" size="small" :split="false" bordered>
            <template #renderItem="{ item }">
              <a-list-item>
                <span class="step-output-label">{{ item.label }}</span>
                <span class="step-output-value">{{ item.value }}</span>
              </a-list-item>
            </template>
          </a-list>
        </div>

        <!-- 活动历史 -->
        <div class="step-detail-section">
          <div class="step-detail-section-title">活动历史</div>
          <a-empty v-if="!stepDetailHistory.length" description="暂无活动记录" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
          <a-timeline v-else>
            <a-timeline-item v-for="(h, idx) in stepDetailHistory" :key="idx">
              <div class="step-history-head">
                <span class="step-history-step">{{ h.step }}</span>
                <span v-if="h.timestamp" class="step-history-time">{{ new Date(h.timestamp).toLocaleString() }}</span>
              </div>
              <div v-if="h.message" class="step-history-msg">{{ h.message }}</div>
              <div v-if="h.order_id" class="step-history-meta">
                <a-tag color="blue">订单 {{ h.order_id }}</a-tag>
              </div>
              <div v-if="h.error" class="step-history-error">{{ h.error }}</div>
            </a-timeline-item>
          </a-timeline>
        </div>

        <!-- 下一步操作引导 -->
        <div v-if="currentStep === stepDetailKey && ecmlStore.state?.blocked_reason" class="step-detail-cta">
          <a-alert type="warning" show-icon message="该步骤需要人工干预" :description="ecmlStore.state.blocked_reason" />
        </div>
      </div>
      <EmptyState v-else type="data" description="请点击上方流程节点查看详情" />
    </a-drawer>

  </div>
</template>

<script setup>
import { ref, reactive, computed, h, onMounted, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Empty } from 'ant-design-vue'
import {
  HistoryOutlined,
} from '@ant-design/icons-vue'
import { useECMLStore } from '@/stores/ecml'
import { getOptions } from '@/api/properties'
import { getExperimentAnalysis, listExperimentResults } from '@/api/experiments'
import { getEcmlRuns, getECMLNextRound } from '@/api/ecml'
import client from '@/api/client'
import { formatSci } from '@/utils/format'
import ScientificNotation from '@/components/ScientificNotation.vue'
import { useMdmDict, useUnitSymbols } from '@/utils/mdmDict'
import { getSourceBadge } from '@/utils/candidateSource'
import { DEFAULT_MULTI_OBJECTIVE_CONFIG, MULTI_OBJECTIVE_OPTIONS } from '@/constants/objectiveConfig'
import { ECML_RECOMMENDED_TARGET_KEY, ECML_RECOMMENDED_CANDIDATE_KEY } from '@/utils/researchContext'
import ECMLStepFlow from '@/components/ECMLStepFlow.vue'
import MoleculeView from '@/components/MoleculeView.vue'
import ParetoChart from '@/components/ParetoChart.vue'
import RadarChart from '@/components/RadarChart.vue'
import ResearchContextBanner from '@/components/ResearchContextBanner.vue'
import EmptyState from '@/components/EmptyState.vue'
import ECMLControlPanel from '@/components/ecml/ECMLControlPanel.vue'
import ECMLStrategyPanel from '@/components/ecml/ECMLStrategyPanel.vue'
import ECMLRoundResult from '@/components/ecml/ECMLRoundResult.vue'
import ECMLCommitteePanel from '@/components/ecml/ECMLCommitteePanel.vue'
import ECMLResultOverview from '@/components/ecml/ECMLResultOverview.vue'
import { startECMLRound, listECMLRounds, getECMLRound, confirmECMLRound } from '@/api/ecml'

const ecmlStore = useECMLStore()
const route = useRoute()
const router = useRouter()

// 从 MDM 加载单位符号（失败时 computed 使用默认单位兜底）
const { symbols: unitSymbols, load: loadUnitSymbols } = useUnitSymbols()
const condUnit = computed(() => unitSymbols.value.conductivity || 'S/cm')
const massUnit = computed(() => unitSymbols.value.mass || 'kg')
const energyUnit = computed(() => unitSymbols.value.energy || 'eV')
const energyPerAtomUnit = computed(() => unitSymbols.value.energy_per_atom || 'eV/atom')

const LAST_FORM_KEY = 'battery_emcl:last_form'
const currentScenarioId = ref('')

// 前置条件检查：ECML 闭环迭代需要至少 1 条实验数据
const experimentDataCount = ref(0)
const prerequisitesMet = computed(() => experimentDataCount.value > 0)
const prerequisiteMessage = computed(() => {
  if (experimentDataCount.value === 0) return '无实验数据'
  return ''
})
const prerequisiteDetail = computed(() => {
  if (experimentDataCount.value === 0) {
    return 'ECML 闭环迭代需要至少 1 条实验数据，请先在实验数据页录入或导入数据'
  }
  return ''
})

async function loadExperimentDataCount() {
  try {
    const res = await listExperimentResults({ limit: 1 })
    if (Array.isArray(res)) {
      experimentDataCount.value = res.length
    } else if (Array.isArray(res?.items)) {
      experimentDataCount.value = res.items.length
    } else if (res?.total != null) {
      experimentDataCount.value = Number(res.total) || 0
    } else {
      experimentDataCount.value = 0
    }
  } catch {
    experimentDataCount.value = 0
  }
}

const form = reactive({
  target: 'LiCoO2',
  target_property: 'ionic_conductivity',
  max_iterations: 3,
  optimize_mode: 'single', // 'single' | 'multi'
  multi_objective_props: [], // 多目标模式下选中的属性 key 列表
})

// Result Overview 子组件引用（用于读取 bestCandidate/noResult）
const resultOverviewRef = ref(null)

// 多目标优化可选项与配置（统一来自 objectiveConfig，避免硬编码漂移）
const multiObjectiveOptions = [...MULTI_OBJECTIVE_OPTIONS]

// 多目标配置：父组件持有，传给 ECMLControlPanel 作为 props
const multiObjectiveConfig = reactive({ ...DEFAULT_MULTI_OBJECTIVE_CONFIG })

const cancelled = ref(false)
const error = ref('')

// 计时器相关
const startTime = ref(null)
const elapsed = ref(0)
let _timer = null

// 异步轮询相关
const pollingTimer = ref(null)
const pollingCount = ref(0)
const runStatus = ref('') // '' | 'running' | 'completed' | 'timeout' | 'failed'
const MAX_POLLING = 40 // 120秒 / 3秒 ≈ 40 次
const POLLING_INTERVAL = 3000

const RUN_STEP_OPTIONS_DEFAULT = [
  { label: 'Step 1 材料路由', value: 'step1_route' },
  { label: 'Step 2 候选生成', value: 'step2_generate' },
  { label: 'Step 3a 合成检查', value: 'step3_synthesis_check' },
  { label: 'Step 3b 工业化验证', value: 'step3_industrialization' },
  { label: 'Step 4 性质预测', value: 'step4_predict' },
  { label: 'Step 5 DFT 验证', value: 'step5_verify' },
  { label: 'Step 6 实验', value: 'step6_experiment' },
  { label: 'Step 7 反馈优化', value: 'step7_feedback' },
  { label: '等待实验数据', value: 'waiting_for_data' },
]
const runStepOptions = ref([...RUN_STEP_OPTIONS_DEFAULT])

const currentStepLabel = computed(() => {
  const history = Array.isArray(ecmlStore.state?.history) ? ecmlStore.state.history : []
  const last = history[history.length - 1]
  if (!last) return '初始化…'
  const opt = runStepOptions.value.find((o) => o.value === last.step)
  if (opt) return opt.label
  const fallback = Object.fromEntries(RUN_STEP_OPTIONS_DEFAULT.map((o) => [o.value, o.label]))
  return fallback[last.step] || last.step || '执行中…'
})

function formatElapsed(s) {
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

async function loadMdmOptions() {
  const { statusOptions } = useMdmDict()
  const loaded = await statusOptions('run')
  if (loaded.length) {
    runStepOptions.value = loaded
  } else {
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
}

// 中间结果查看
const showIntermediate = ref(false)

const propertyOptions = ref([])
const propertyOptionsCtrl = new AbortController()

onMounted(async () => {
  // 从 MDM 加载执行状态选项
  await loadMdmOptions()
  // 从 MDM 加载单位符号（失败时 computed 使用默认单位兜底）
  await loadUnitSymbols()

  // 加载属性选项
  try {
    const res = await getOptions({ usable_in: 'ecml_target' }, { signal: propertyOptionsCtrl.signal })
    propertyOptions.value = res.options
  } catch (e) {
    if (e.name === 'AbortError' || e.code === 'ERR_CANCELED' || e.message === 'canceled') return
    propertyOptions.value = [
      { label: '离子电导率', value: 'ionic_conductivity' },
      { label: '带隙', value: 'band_gap' },
      { label: '形成能', value: 'formation_energy' },
    ]
  }

  // 加载迭代历史（B3.4）
  fetchIterationHistory()

  // 前置条件检查：加载实验数据数量
  loadExperimentDataCount()

  // 优先从 URL run_id 恢复状态
  const runId = route.query.run_id
  if (runId) {
    try {
      const res = await ecmlStore.restoreRun(runId)
      if (res?.target) {
        form.target = res.target
      }
      if (res?.target_property) {
        form.target_property = res.target_property
      }
      if (!res?.is_complete) {
        pollingActive.value = true
        ecmlStore.startPolling(runId)
        message.info('已恢复 ECML 运行，正在轮询进度…')
      } else {
        message.success(`ECML 运行已恢复，共 ${res.iterations || 0} 次迭代`)
        // 已完成的运行：获取下一轮候选建议（B3.5）
        fetchNextRoundSuggestions(runId)
      }
    } catch (e) {
      // 前端 axios 已设置 skipErrorNotification=false（默认），但 404 场景仍需用户可感知
      const status = e?.response?.status
      if (status === 404) {
        error.value = `未找到运行记录「${runId}」，请检查链接或新建运行。`
      } else {
        error.value = e?.response?.data?.detail || '恢复 ECML 运行状态失败'
      }
    }
    return
  }

  // 无 run_id 时：P3-2 研发工作台派生上下文优先，其次 sessionStorage 恢复
  const qTarget = route.query.target
  const qProp = route.query.target_property
  const qMulti = route.query.multi_props
  if (qTarget) form.target = String(qTarget)
  if (qMulti) {
    form.optimize_mode = 'multi'
    form.multi_objective_props = String(qMulti).split(',').filter(Boolean)
  } else if (qProp) {
    form.optimize_mode = 'single'
    form.target_property = String(qProp)
  }
  // P0-001：保存场景 ID 供下游传递
  if (route.query.scenario_id) {
    currentScenarioId.value = String(route.query.scenario_id)
  }
  if (qTarget || qProp || qMulti) return

  // 无派生上下文时从 sessionStorage 恢复上次表单
  try {
    const saved = sessionStorage.getItem(LAST_FORM_KEY)
    if (saved) {
      const obj = JSON.parse(saved)
      if (obj.target) form.target = obj.target
      if (obj.target_property) form.target_property = obj.target_property
      if (obj.max_iterations) form.max_iterations = obj.max_iterations
      if (obj.optimize_mode) form.optimize_mode = obj.optimize_mode
      if (Array.isArray(obj.multi_objective_props)) form.multi_objective_props = obj.multi_objective_props
    }
  } catch { /* ignore */ }
})

// 后端 history step 名 → 前端步骤 key 的映射
const stepKeyMap = {
  route: 'step1_route',
  generate: 'step2_generate',
  synthesis_check: 'step3_industrialization',
  industrialization: 'step3_industrialization',
  predict: 'step4_predict',
  verify: 'step5_verify',
  experiment: 'step6_experiment',
  feedback: 'step7_feedback',
}

const stepOrder = [
  'step1_route',
  'step2_generate',
  'step3_industrialization',
  'step4_predict',
  'step5_verify',
  'step6_experiment',
  'step7_feedback',
]

// 基于后端 state.history 真实执行记录，提取已完成的步骤 key
const completedSteps = computed(() => {
  const history = Array.isArray(ecmlStore.state?.history) ? ecmlStore.state.history : []
  const completed = new Set()
  for (const item of history) {
    const key = stepKeyMap[item?.step]
    if (key) completed.add(key)
  }
  return Array.from(completed)
})

// is_complete 为 true 时无当前步骤；否则取第一个未完成的步骤为"进行中"（蓝色脉冲）
const currentStep = computed(() => {
  if (!ecmlStore.state || ecmlStore.state.is_complete) return ''
  for (const key of stepOrder) {
    if (!completedSteps.value.includes(key)) return key
  }
  return ''
})

// 失败/需人工干预的步骤：运行失败或超时时，当前停留在的步骤标记为红色
const failedSteps = computed(() => {
  if (!ecmlStore.state || ecmlStore.state.is_complete) return []
  // 运行失败/超时时，当前进行中的步骤即为失败步骤
  if (runStatus.value === 'failed' || runStatus.value === 'timeout') {
    return currentStep.value ? [currentStep.value] : []
  }
  // blocked_reason 存在时，当前步骤需要人工干预
  if (ecmlStore.state?.blocked_reason && currentStep.value) {
    return [currentStep.value]
  }
  return []
})

// 可点击查看详情的步骤：所有已完成 + 当前进行中 + 失败的步骤
const clickableSteps = computed(() => {
  const set = new Set([...completedSteps.value, ...failedSteps.value])
  if (currentStep.value) set.add(currentStep.value)
  return Array.from(set)
})

// 步骤详情抽屉
const stepDetailVisible = ref(false)
const stepDetailKey = ref('')
const stepDetailTitle = computed(() => {
  const opt = runStepOptions.value.find((o) => o.value === stepDetailKey.value)
  return opt?.label || '步骤详情'
})
// 当前选中步骤的历史记录条目
const stepDetailHistory = computed(() => {
  if (!stepDetailKey.value) return []
  const history = Array.isArray(ecmlStore.state?.history) ? ecmlStore.state.history : []
  return history.filter((h) => stepKeyMap[h?.step] === stepDetailKey.value)
})
// 当前选中步骤的输出产物（候选/工业化/预测/验证/实验/反馈）
const stepDetailOutputs = computed(() => {
  if (!stepDetailKey.value) return []
  const outputs = []
  const s = ecmlStore.state || {}
  if (stepDetailKey.value === 'step2_generate' || stepDetailKey.value === 'step1_route') {
    const count = Array.isArray(s.candidates) ? s.candidates.length : 0
    if (count) outputs.push({ label: '候选材料', value: `${count} 个` })
  }
  if (stepDetailKey.value === 'step3_industrialization') {
    const count = Array.isArray(s.synthesizable) ? s.synthesizable.length : 0
    if (count) outputs.push({ label: '工业化通过', value: `${count} 个` })
  }
  if (stepDetailKey.value === 'step4_predict') {
    const count = Array.isArray(s.predictions) ? s.predictions.length : 0
    if (count) outputs.push({ label: '性质预测', value: `${count} 条` })
  }
  if (stepDetailKey.value === 'step5_verify') {
    const count = Array.isArray(s.verified) ? s.verified.length : 0
    if (count) outputs.push({ label: 'DFT 验证', value: `${count} 条` })
  }
  if (stepDetailKey.value === 'step6_experiment') {
    const count = Array.isArray(s.experiment_results) ? s.experiment_results.length : 0
    if (count) outputs.push({ label: '实验结果', value: `${count} 条` })
  }
  if (stepDetailKey.value === 'step7_feedback' && s.feedback) {
    if (s.feedback.summary) outputs.push({ label: '反馈总结', value: s.feedback.summary })
  }
  return outputs
})

function onStepClick(key) {
  stepDetailKey.value = key
  stepDetailVisible.value = true
}

// ---- ECML 运行结果详细展示 ----
const detailCandidates = computed(() => Array.isArray(ecmlStore.state?.candidates) ? ecmlStore.state.candidates : [])
const detailSynthesizable = computed(() => Array.isArray(ecmlStore.state?.synthesizable) ? ecmlStore.state.synthesizable : [])
const detailPredictions = computed(() => Array.isArray(ecmlStore.state?.predictions) ? ecmlStore.state.predictions : [])
const detailVerified = computed(() => Array.isArray(ecmlStore.state?.verified) ? ecmlStore.state.verified : [])
const detailExperiments = computed(() => Array.isArray(ecmlStore.state?.experiment_results) ? ecmlStore.state.experiment_results : [])
const detailFeedback = computed(() => {
  const f = ecmlStore.state?.feedback
  return f && typeof f === 'object' ? f : null
})

// ---- 结果概览相关 computed 已迁移至 ECMLResultOverview 子组件 ----
// noResult 直接复用子组件暴露的计算结果，避免逻辑重复
const noResult = computed(() => resultOverviewRef.value?.noResult ?? false)

// 实验分析简报：从 ECML 状态中尝试提取 order_id，命中则拉取分析简报
const ecmlOrderId = computed(() => {
  const results = Array.isArray(ecmlStore.state?.experiment_results) ? ecmlStore.state.experiment_results : []
  for (const r of results) {
    if (r.order_id) return r.order_id
  }
  const history = Array.isArray(ecmlStore.state?.history) ? ecmlStore.state.history : []
  for (const h of history) {
    if (h.order_id) return h.order_id
  }
  return ''
})
const ecmlAnalysisBrief = ref(null)
watch(ecmlOrderId, async (orderId) => {
  ecmlAnalysisBrief.value = null
  if (!orderId) return
  try {
    ecmlAnalysisBrief.value = await getExperimentAnalysis(orderId)
  } catch {
    ecmlAnalysisBrief.value = null
  }
}, { immediate: true })

// currentRunId declared here (before the watch that uses it) to avoid TDZ errors
const currentRunId = computed(() => route.query.run_id || ecmlStore.state?.run_id || '')

// ---- 贝叶斯优化 Round 决策引擎（一期/二期：策略启动 → 复核下发）----
const boRound = ref(null) // 当前最新一轮 BO 推荐结果

// 当前采集函数（由策略面板同步）。多目标 + EHVI 时隐藏权重字段（帕累托优化，权重无效）
const currentAcquisition = ref('ei')
const hideObjectiveWeights = computed(
  () => form.optimize_mode === 'multi' && currentAcquisition.value === 'ehvi'
)

async function onStrategyStart(payload) {
  if (!currentRunId.value) {
    message.warning('请先在顶部配置并启动一轮 ECML 运行，再启动 BO 推荐')
    return
  }
  try {
    const res = await startECMLRound(currentRunId.value, payload)
    boRound.value = res
    message.success(`第 ${res.round_no || 1} 轮 BO 推荐已产出，等待课题负责人复核`)
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '启动 BO 推荐失败'
    message.error(error.value)
  }
}

async function onRoundConfirmed(result) {
  try {
    if (boRound.value?.round_id) {
      boRound.value = await getECMLRound(boRound.value.round_id)
    }
    message.success('已确认下发，实验任务已生成')
  } catch {
    message.success('已确认下发')
  }
}

// Committee cases / DFT 队列相关 watch 与函数已迁移至 ECMLCommitteePanel 子组件

// 属性 key → 候选字段映射
const ECML_FIELD_MAP = {
  ionic_conductivity: 'predicted_ionic_conductivity',
  band_gap: 'band_gap',
  formation_energy: 'formation_energy',
  stability: 'stability_score',
  energy_above_hull: 'energy_above_hull',
}

const hasMultiObjective = computed(() => {
  return form.optimize_mode === 'multi' && form.multi_objective_props.length > 0 && detailCandidates.value.length > 0
})

const candidatesWithObjectives = computed(() => {
  if (!hasMultiObjective.value) return []
  const props_keys = form.multi_objective_props
  return detailCandidates.value.map((c) => {
    const objectives = props_keys
      .map((key) => {
        const fieldName = ECML_FIELD_MAP[key] || key
        const opt = multiObjectiveOptions.find((o) => o.value === key)
        const cfg = multiObjectiveConfig[key] || { weight: 0.5, direction: 'maximize', min: null, max: null }
        return {
          name: opt ? opt.label : key,
          key,
          value: c[fieldName],
          direction: cfg.direction,
          weight: cfg.weight,
          min: cfg.min,
          max: cfg.max,
        }
      })
      .filter((o) => o.value != null)
    return { ...c, objectives }
  })
})

function onChartSelect(candidate) {
  message.info(`已选中候选材料：${candidate.name || candidate.formula || candidate.smiles}`)
}

const moObjectivesForTable = computed(() => {
  if (!hasMultiObjective.value) return []
  return form.multi_objective_props.map((key) => {
    const opt = multiObjectiveOptions.find((o) => o.value === key)
    const cfg = multiObjectiveConfig[key] || {}
    return {
      key: ECML_FIELD_MAP[key] || key,
      name: opt ? opt.label : key,
      min: cfg.min,
      max: cfg.max,
    }
  })
})

function getMoStatus(record, obj) {
  const val = record[obj.key]
  if (val == null) return true
  if (obj.min != null && val < obj.min) return false
  if (obj.max != null && val > obj.max) return false
  return true
}

// 将 DFT 验证通过的材料发送到下一步
function sendVerifiedToExperiment() {
  const verified = detailVerified.value
  if (!verified.length) {
    message.warning('暂无验证材料可发送')
    return
  }
  // 优先取第一个验证收敛的材料
  const target = verified.find((v) => v.verification_converged) || verified[0]
  const formula = target.formula || target.candidate || target.smiles || ''
  const query = { formula }
  if (currentScenarioId.value) query.scenario_id = currentScenarioId.value
  router.push({ path: '/experiments', query })
  message.info('已发送到实验数据页面')
}

function sendVerifiedToFormula() {
  const verified = detailVerified.value
  if (!verified.length) {
    message.warning('暂无验证材料可发送')
    return
  }
  const target = verified.find((v) => v.verification_converged) || verified[0]
  const targetMaterial = target.smiles || target.formula || target.candidate || ''
  const query = { target: targetMaterial }
  if (currentScenarioId.value) query.scenario_id = currentScenarioId.value
  router.push({ path: '/formula-design', query })
  message.info('已发送到配方页面')
}

function sendBestToExperiment(best) {
  if (!best) {
    message.warning('暂无推荐候选材料')
    return
  }
  const formula = best.formula || best.smiles || best.psmiles || ''
  const query = { formula }
  if (currentScenarioId.value) query.scenario_id = currentScenarioId.value
  router.push({ path: '/experiments', query })
  message.info('已将推荐候选材料发送到实验页面')
}

function sendBestToFormula(best) {
  if (!best) {
    message.warning('暂无推荐候选材料')
    return
  }
  const targetMaterial = best.smiles || best.formula || best.psmiles || ''
  const query = { target: targetMaterial }
  if (currentScenarioId.value) query.scenario_id = currentScenarioId.value
  router.push({ path: '/formula-design', query })
  message.info('已将推荐候选材料发送到配方页面')
}

function scrollToDetail(sectionId) {
  const el = document.getElementById(`ecml-detail-${sectionId}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const candidateColumns = computed(() => {
  const cols = [
    { title: '分子图谱', key: 'molecule', width: 160, align: 'center' },
    { title: '名称', dataIndex: 'name', key: 'name', width: 160, ellipsis: true },
    { title: 'SMILES', dataIndex: 'smiles', key: 'smiles', ellipsis: true },
    { title: '来源', dataIndex: 'source', key: 'source', width: 120, ellipsis: true },
    { title: '证据标签', key: 'provenance', width: 130, align: 'center' },
    { title: `预测电导率 (${condUnit.value})`, dataIndex: 'predicted_ionic_conductivity', key: 'cond', width: 160, align: 'right', className: 'num-cell', customRender: ({ text }) => h(ScientificNotation, { value: text, property: 'predicted_ionic_conductivity' }) },
    { title: '工业化', key: 'industrial', width: 120, align: 'center' },
  ]
  if (hasMultiObjective.value) {
    cols.push({ title: '达标状态', key: 'mo_status', width: form.multi_objective_props.length * 70 })
  }
  return cols
})

const synthesizableColumns = [
  { title: '名称', dataIndex: 'name', key: 'name', width: 200, ellipsis: true },
  { title: '匹配物料', key: 'matched', ellipsis: true },
  { title: '预估成本', key: 'cost', width: 140, align: 'right', className: 'num-cell' },
  { title: '工业化评分', key: 'score', width: 120, align: 'right', className: 'num-cell' },
]

const predictionColumns = [
  { title: '分子图谱', key: 'molecule', width: 160, align: 'center' },
  { title: '材料标识', key: 'material', ellipsis: true },
  { title: '预测值', key: 'value', width: 140, align: 'right', className: 'num-cell' },
  { title: '属性', dataIndex: 'property_name', key: 'property', width: 140, ellipsis: true },
  { title: '方法', dataIndex: 'method', key: 'method', width: 120, ellipsis: true },
  { title: '模型', dataIndex: 'model', key: 'model', width: 140, ellipsis: true },
  { title: '证据标签', key: 'provenance_badge', width: 130, align: 'center' },
]

const verifiedColumns = [
  { title: '材料标识', key: 'material', ellipsis: true },
  { title: '验证方法', dataIndex: 'verification_method', key: 'vmethod', width: 160, ellipsis: true },
  { title: '验证值', key: 'vvalue', width: 160, align: 'right', className: 'num-cell' },
  { title: '收敛', key: 'converged', width: 100, align: 'center' },
  { title: '证据标签', key: 'provenance_badge', width: 130, align: 'center' },
]

const experimentColumns = [
  { title: '候选材料', dataIndex: 'candidate', key: 'candidate', width: 200, ellipsis: true },
  { title: '测量类型', dataIndex: 'measurement_type', key: 'mtype', width: 160, ellipsis: true },
  { title: '值', key: 'value', width: 140, align: 'right', className: 'num-cell' },
  { title: '状态', key: 'status', width: 120, align: 'center' },
]

const candidateRowKey = (r) => r.name || r.smiles || r.formula || ''
const synthesizableRowKey = (r) => r.name || r.smiles || r.formula || ''
const predictionRowKey = (r) => `${r.smiles || r.formula || ''}|${r.property_name || ''}|${r.method || ''}`
const verifiedRowKey = (r) => `${r.smiles || r.formula || ''}|${r.verification_method || ''}`
const experimentRowKey = (r) => `${r.candidate || ''}|${r.measurement_type || ''}`

const synthesizableExpandable = {
  rowExpandable: (record) => {
    const r = record.industrial_recipe
    return !!(r && ((Array.isArray(r.bom) && r.bom.length) || (Array.isArray(r.bop) && r.bop.length)))
  },
}

function safeCount(v) {
  if (Array.isArray(v)) return v.length
  if (typeof v === 'number' && !isNaN(v)) return v
  return 0
}

function trendColor(trend) {
  const map = { '上升': 'green', '下降': 'red', '稳定': 'blue' }
  return map[trend] || 'default'
}

function formatCost(cost) {
  if (cost == null || cost === '' || isNaN(cost)) return '-'
  return `¥${Number(cost).toFixed(2)}/${massUnit.value}`
}

function formatScore(score) {
  if (score == null || score === '') return '-'
  const n = Number(score)
  if (isNaN(n)) return '-'
  // 约定 score 范围 [0, 1]，超过 1 视为已是 0-100 范围
  const pct = n >= 0 && n <= 1 ? n * 100 : n
  return `${pct.toFixed(1)}%`
}

function formatValueUnit(value, unit) {
  if (value == null || value === '') return '-'
  // 数值型统一按 4 位有效数字截断（小量级自动转科学计数法），避免原始浮点直出
  const isNumeric = typeof value === 'number' || (typeof value === 'string' && value.trim() !== '' && !isNaN(Number(value)))
  const formatted = isNumeric ? formatSci(value, 4) : String(value)
  return unit ? `${formatted} ${unit}` : formatted
}

function materialLabel(record) {
  return record.formula || record.smiles || record.psmiles || '-'
}

function matchedMaterialsText(record) {
  const m = record.matched_materials
  if (!m) return '-'
  if (Array.isArray(m)) return m.join(', ') || '-'
  return String(m)
}

function snakeToTitle(s) {
  return String(s)
    .split('_')
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function columnsFromData(arr) {
  if (!Array.isArray(arr) || arr.length === 0) return []
  return Object.keys(arr[0]).map((k) => ({
    title: snakeToTitle(k),
    dataIndex: k,
    key: k,
    ellipsis: true,
  }))
}

function rejectReasonText(reasons) {
  if (!reasons) return ''
  return Array.isArray(reasons) ? reasons.join('；') : String(reasons)
}

// ---- 证据标签 & 审计 ----
const showAuditModal = ref(false)
const auditSummary = ref(null)

function evidenceLevelColor(level) {
  const map = { primary: 'green', computed: 'blue', auxiliary: 'orange', draft: 'default' }
  return map[level] || 'default'
}

function evidenceLevelLabel(level) {
  const map = { primary: '本地模型', computed: 'InternLM 建议', auxiliary: 'SCP 辅助计算', draft: '草案' }
  return map[level] || level || '未知'
}

function provenanceLabel(prov) {
  if (!prov) return '未知'
  // If provenance has a source field, use it for the label
  if (prov.source === 'internlm') return 'InternLM 建议'
  if (prov.source === 'scp') return 'SCP 辅助计算'
  if (prov.source === 'local') return '本地模型'
  return evidenceLevelLabel(prov.evidence_level)
}

async function showAudit(prov) {
  auditSummary.value = prov
  showAuditModal.value = true
  // If there's an invocation_id, try to fetch full details
  if (prov?.invocation_id) {
    try {
      const detail = await client.get(`/integrations/invocations/${prov.invocation_id}`)
      auditSummary.value = { ...prov, ...detail }
    } catch {
      // Fall back to provenance data
    }
  }
}

// ---- 迭代历史 & 下一轮候选建议（B3.4/B3.5）----
const iterationHistory = ref([])
const nextRoundSuggestions = ref(null)
const startingNextRound = ref(false)

const iterationHistoryColumns = [
  { title: '轮次', key: 'iteration_id', width: 100 },
  { title: '目标', dataIndex: 'target', key: 'target', ellipsis: true },
  { title: '迭代数', dataIndex: 'iteration', key: 'iteration', width: 80 },
  { title: '状态', key: 'status', width: 100 },
  { title: '更新时间', key: 'updated_at', width: 180 },
  { title: '操作', key: 'action', width: 120 },
]

const nextRoundColumns = [
  { title: '名称', dataIndex: 'name', key: 'name', width: 200, ellipsis: true },
  { title: 'SMILES/Formula', key: 'identifier', ellipsis: true },
  { title: '策略', key: 'strategy', width: 100 },
  { title: '质量', key: 'data_quality', width: 90 },
  { title: '推荐理由', dataIndex: 'reasoning', key: 'reasoning', ellipsis: true },
  { title: '预期性能', key: 'expected_performance', width: 120, align: 'right' },
  { title: '下一步', key: 'action', width: 180, align: 'center' },
]

async function fetchIterationHistory() {
  try {
    const data = await getEcmlRuns(50)
    const runs = Array.isArray(data?.runs) ? data.runs : []
    iterationHistory.value = runs.sort((a, b) => (a.iteration_id || 1) - (b.iteration_id || 1))
  } catch {
    iterationHistory.value = []
  }
}

async function fetchNextRoundSuggestions(runId) {
  if (!runId) {
    nextRoundSuggestions.value = null
    return
  }
  try {
    nextRoundSuggestions.value = await getECMLNextRound(runId)
  } catch {
    nextRoundSuggestions.value = null
  }
}

async function viewIteration(record) {
  const query = { run_id: record.run_id }
  if (currentScenarioId.value) query.scenario_id = currentScenarioId.value
  router.push({ path: '/ecml', query })
  try {
    const res = await ecmlStore.restoreRun(record.run_id)
    if (res?.target) form.target = res.target
    if (res?.target_property) form.target_property = res.target_property
    if (res?.is_complete) {
      fetchNextRoundSuggestions(record.run_id)
    } else if (res?.run_id) {
      pollingActive.value = true
      ecmlStore.startPolling(res.run_id)
    }
  } catch {
    message.error('恢复 ECML 运行状态失败')
  }
}

async function onStartNextRound() {
  if (!currentRunId.value) return
  startingNextRound.value = true
  try {
    const target = ecmlStore.state?.target || form.target
    const targetProperty = ecmlStore.state?.target_property || form.target_property
    const maxIterations = form.max_iterations
    let targetProperties = null
    if (form.optimize_mode === 'multi' && form.multi_objective_props.length > 0) {
      targetProperties = form.multi_objective_props.map((prop) => {
        const cfg = multiObjectiveConfig[prop] || { weight: 0.5, direction: 'maximize', min: null, max: null }
        return { property: prop, weight: cfg.weight, direction: cfg.direction, min: cfg.min, max: cfg.max }
      })
    }
    cancelled.value = false
    startTime.value = Date.now()
    _timer = setInterval(() => {
      elapsed.value = Math.floor((Date.now() - startTime.value) / 1000)
    }, 1000)
    const res = await ecmlStore.run(target, targetProperty, maxIterations, targetProperties, currentRunId.value, currentScenarioId.value)
    if (res?.run_id && !res.is_complete) {
      const query = { run_id: res.run_id }
      if (currentScenarioId.value) query.scenario_id = currentScenarioId.value
      router.replace({ path: '/ecml', query })
      message.info(`已启动第 ${res.iteration_id || 1} 轮 ECML 迭代`)
      startComponentPolling(res.run_id)
    } else if (res?.is_complete) {
      runStatus.value = 'completed'
      message.success(`第 ${res.iteration_id || 1} 轮实验闭环迭代完成`)
    }
  } catch (err) {
    stopAllRunTimers()
    error.value = err.response?.data?.detail || err.message || '启动下一轮失败'
  } finally {
    startingNextRound.value = false
  }
}

// 将下一轮候选建议发送到候选设计页（通过 sessionStorage 携带推荐目标，页面顶部展示引导提示）
function sendToCandidateDesign(record) {
  const target = record.formula || record.smiles || record.psmiles || record.name || ''
  if (!target) {
    message.warning('该候选材料缺少可识别的 formula/SMILES 标识')
    return
  }
  sessionStorage.setItem(ECML_RECOMMENDED_TARGET_KEY, target)
  router.push({ path: '/workbench' })
}

// 基于下一轮候选建议创建实验任务（通过 sessionStorage 携带候选信息，实验工作台读取后预填 notes 并展示引导）
function createExperimentTask(record) {
  const formula = record.formula || record.smiles || record.psmiles || record.name || ''
  if (!formula) {
    message.warning('该候选材料缺少可识别的 formula/SMILES 标识')
    return
  }
  sessionStorage.setItem(ECML_RECOMMENDED_CANDIDATE_KEY, formula)
  const query = { create: '1' }
  if (currentScenarioId.value) query.scenario_id = currentScenarioId.value
  router.push({ path: '/experiment-workbench', query })
}

const pollingActive = ref(false)

// 停止所有运行相关定时器（轮询 + 计时）
function stopAllRunTimers() {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
  if (_timer) {
    clearInterval(_timer)
    _timer = null
  }
}

// 启动组件级异步轮询：每 POLLING_INTERVAL 毫秒查询一次状态，MAX_POLLING 次后超时
function startComponentPolling(runId) {
  stopAllRunTimers()
  pollingCount.value = 0
  runStatus.value = 'running'
  pollingActive.value = true
  pollingTimer.value = setInterval(async () => {
    pollingCount.value++
    if (pollingCount.value > MAX_POLLING) {
      stopAllRunTimers()
      pollingActive.value = false
      runStatus.value = 'timeout'
      ecmlStore.cancel()
      message.warning('运行超时，请稍后在迭代历史中查看结果')
      return
    }
    try {
      const status = await ecmlStore.pollRun(runId)
      if (status?.is_complete || status?.status === 'completed') {
        stopAllRunTimers()
        runStatus.value = 'completed'
        ecmlStore.cancel()
        // 完成提示与后续动作（fetchNextRoundSuggestions/fetchIterationHistory）由 watch(is_complete) 处理
      } else if (status?.status === 'failed') {
        stopAllRunTimers()
        pollingActive.value = false
        runStatus.value = 'failed'
        ecmlStore.cancel()
        message.error('ECML 运行失败，请稍后重试或联系管理员')
      }
      // running 状态继续轮询
    } catch (err) {
      // 网络错误不停止轮询，继续重试
      if (import.meta.env.DEV) console.error('轮询失败:', err)
    }
  }, POLLING_INTERVAL)
}

async function onRun() {
  cancelled.value = false
  // 前端校验：迭代次数必须为 1-10 的正整数
  const iterNum = Number(form.max_iterations)
  if (!Number.isInteger(iterNum) || iterNum < 1 || iterNum > 10) {
    error.value = '迭代次数必须为 1-10 的正整数'
    return
  }
  startTime.value = Date.now()
  _timer = setInterval(() => {
    elapsed.value = Math.floor((Date.now() - startTime.value) / 1000)
  }, 1000)
  try {
    // 多目标模式：构建 target_properties 配置数组
    let targetProperties = null
    if (form.optimize_mode === 'multi' && form.multi_objective_props.length > 0) {
      targetProperties = form.multi_objective_props.map((prop) => {
        const cfg = multiObjectiveConfig[prop] || { weight: 0.5, direction: 'maximize', min: null, max: null }
        return {
          property: prop,
          weight: cfg.weight,
          direction: cfg.direction,
          min: cfg.min,
          max: cfg.max,
        }
      })
    }
    const res = await ecmlStore.run(form.target, form.target_property, form.max_iterations, targetProperties, null, currentScenarioId.value)
    // 流程图状态由 completedSteps/currentStep computed 基于 state.history 自动驱动
    if (res?.run_id && !res.is_complete) {
      // 后端立即返回 run_id：异步轮询，120 秒超时
      const query = { run_id: res.run_id }
      if (currentScenarioId.value) query.scenario_id = currentScenarioId.value
      router.replace({ path: '/ecml', query })
      message.info('实验闭环迭代已启动，正在轮询进度…')
      startComponentPolling(res.run_id)
    } else if (res?.is_complete) {
      // 同步完成：store 已落 history，这里直接提示
      runStatus.value = 'completed'
      message.success(`实验闭环迭代完成，共 ${res.iterations || 0} 次迭代`)
    } else if (!res?.run_id) {
      // 兼容旧后端：返回值即最终结果但未完成
      message.warning(`实验闭环迭代未完成（is_complete=false），已执行 ${Array.isArray(res?.history) ? res.history.length : 0} 步`)
    }
  } catch (err) {
    stopAllRunTimers()
    // 对用户隐藏技术性报错（err.message 可能是英文），统一展示中文
    error.value = '执行失败，请稍后重试或联系管理员'
  }
}

function onRetry() {
  error.value = ''
  onRun()
}

function onCancel() {
  stopAllRunTimers()
  startTime.value = null
  elapsed.value = 0
  pollingActive.value = false
  runStatus.value = ''
  ecmlStore.cancel()
  cancelled.value = true
  ecmlStore.markCancelled()
  message.info('已取消前端轮询，后端运行可能仍在继续')
}

function onRunAgain() {
  stopAllRunTimers()
  startTime.value = null
  elapsed.value = 0
  ecmlStore.reset()
  cancelled.value = false
  pollingActive.value = false
  runStatus.value = ''
  router.replace({ path: '/ecml' })
}

// 反馈面板"下一步操作"跳转函数
function scrollToResultOverview() {
  const el = document.getElementById('ecml-detail-overview') || document.querySelector('.result-overview-card')
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function restartECML() {
  onRunAgain()
}

function goToCommitteeApproval() {
  router.push({ path: '/my-tasks', query: { tab: 'committee' } })
}

// 保存整个 form 到 sessionStorage
watch(
  () => [form.target, form.target_property, form.max_iterations, form.optimize_mode, form.multi_objective_props],
  () => {
    try {
      sessionStorage.setItem(LAST_FORM_KEY, JSON.stringify({
        target: form.target,
        target_property: form.target_property,
        max_iterations: form.max_iterations,
        optimize_mode: form.optimize_mode,
        multi_objective_props: form.multi_objective_props,
      }))
    } catch { /* ignore */ }
  },
  { deep: true }
)

// 轮询期间 state.is_complete 由 false 变 true 时，触发完成提示并获取下一轮建议
watch(
  () => ecmlStore.state?.is_complete,
  (isComplete) => {
    if (isComplete && pollingActive.value) {
      pollingActive.value = false
      message.success(`实验闭环迭代完成，共 ${ecmlStore.state?.iterations || 0} 次迭代`)
      fetchNextRoundSuggestions(currentRunId.value)
      fetchIterationHistory()
    }
  }
)

onUnmounted(() => {
  stopAllRunTimers()
  pollingActive.value = false
  ecmlStore.cancel()
  propertyOptionsCtrl.abort()
})
</script>

<style scoped>
.ecml-monitor {
  width: 100%;
  max-width: 100%;
}

.ecml-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title-row .page-title {
  margin: 0;
}

.control-card,
.flow-card {
  background: var(--light-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-card);
  margin-bottom: 16px;
}

.control-card :deep(.ant-form-item) {
  margin-bottom: 12px;
}

.control-card :deep(.ant-input-number-input) {
  font-variant-numeric: tabular-nums;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.card-title-row,
.flow-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.flow-title :deep(.ant-tag) {
  margin: 0;
}

@media (max-width: 768px) {
  .summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.progress-info {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: var(--primary-bg);
  border: 1px solid var(--primary-border);
  border-radius: var(--radius);
  font-size: 13px;
  color: var(--text-secondary);
}

.current-step {
  color: var(--text-primary);
  font-weight: 500;
}

.elapsed-time {
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
}

.result-overview-card {
  background: var(--light-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-card);
  margin-bottom: 16px;
}

.detail-card {
  background: var(--light-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-card);
  margin-bottom: 16px;
}

.detail-card :deep(.num-cell) {
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
  color: var(--text-primary);
}

.detail-card :deep(.ant-table-thead > tr > th) {
  background: var(--light-bg-hover) !important;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.detail-card :deep(.ant-table-tbody > tr > td) {
  font-size: 13px;
}

.chart-tabs {
  margin-bottom: 8px;
}

.chart-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 8px;
}

.mo-status-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.mo-status-tag {
  margin: 0;
  font-size: 11px;
  line-height: 18px;
}

.text-muted {
  color: var(--text-muted);
}

.recipe-detail {
  padding: 4px 0;
}

.recipe-block {
  margin-bottom: 16px;
}

.recipe-block:last-child {
  margin-bottom: 0;
}

.recipe-subtitle {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.feedback-block {
  margin-bottom: 16px;
}

.feedback-block:last-child {
  margin-bottom: 0;
}

.feedback-next-actions {
  margin-top: 16px;
  padding: 12px;
  background: var(--primary-bg);
  border: 1px solid var(--primary-border);
  border-radius: var(--radius);
}

.feedback-next-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.stat-card {
  text-align: center;
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary, #595959);
  margin-bottom: 4px;
}

.analysis-subtitle {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin-bottom: 6px;
}

.provenance-badge {
  cursor: pointer;
  margin: 0;
}

.provenance-badge:hover {
  opacity: 0.8;
}

/* 前置条件横幅 */
.prerequisite-banner {
  margin-bottom: 16px;
}

/* 步骤详情抽屉 */
.step-detail-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.step-detail-desc {
  margin-bottom: 4px;
}

.step-blocked-reason {
  color: var(--error, #ff4d4f);
  font-weight: 500;
}

.step-detail-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.step-output-label {
  color: var(--text-secondary);
  flex: 1;
}

.step-output-value {
  color: var(--text-primary);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.step-history-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.step-history-step {
  font-weight: 600;
  color: var(--text-primary);
}

.step-history-time {
  color: var(--text-muted);
  font-size: 12px;
  margin-left: auto;
}

.step-history-msg {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.step-history-meta {
  margin-top: 4px;
}

.step-history-error {
  margin-top: 4px;
  font-size: 12px;
  color: var(--error, #ff4d4f);
}

.step-detail-cta {
  margin-top: 4px;
}
</style>
