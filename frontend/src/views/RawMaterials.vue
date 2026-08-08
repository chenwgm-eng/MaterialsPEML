<template>
  <div class="raw-materials">
    <div class="page-header">
      <h1 class="page-title">物料规格库</h1>
      <p class="page-subtitle">工业化配方验证层的数据基座 — 基材、锂盐、填料等企业级物料库存与合规信息</p>
    </div>

    <!-- 筛选 -->
    <a-card class="filter-card" :bordered="false">
      <a-form layout="inline">
        <a-form-item label="物料分类">
          <a-select
            v-model:value="filterCategory"
            :options="categoryOptions"
            placeholder="全部分类"
            style="width: 180px"
            allow-clear
            @change="onQuery"
          />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" :loading="loading" @click="onQuery">
            <SearchOutlined /> 查询
          </a-button>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 汇总卡片 -->
    <div class="stat-row" v-if="materials.length > 0">
      <div class="stat-item">
        <span class="stat-value">{{ materials.length }}</span>
        <span class="stat-label">物料总数</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ formatCost(totalCost) }}</span>
        <span class="stat-label">平均单价 (元/{{ massUnit }})</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ reachCompliantCount }}/{{ materials.length }}</span>
        <span class="stat-label">
          REACH 合规
          <a-tag color="purple" class="ai-badge-mini">AI</a-tag>
        </span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ toxicCount }}</span>
        <span class="stat-label">有毒物料</span>
      </div>
    </div>

    <!-- 物料表格 -->
    <a-card class="table-card" :bordered="false">
      <template #title>
        <div class="card-title-row">
          <span class="card-title-text">物料清单</span>
          <a-tag color="blue" class="count-tag">{{ materials.length }} 条</a-tag>
        </div>
      </template>
      <template #extra>
        <a-space>
          <a-tooltip title="新增物料规格将立即写入企业物料库，用于配方生成与可得性检查">
            <a-button type="primary" size="small" @click="onAdd">
              <PlusOutlined /> 新增物料
            </a-button>
          </a-tooltip>
          <a-tooltip :title="selectedMaterial ? '' : '请先选择一行物料'">
            <a-button size="small" :disabled="!selectedMaterial" @click="onEdit">
              <EditOutlined /> 编辑
            </a-button>
          </a-tooltip>
          <a-tooltip :title="selectedMaterial ? '' : '请先选择一行物料'">
            <a-button size="small" type="link" :disabled="!selectedMaterial" @click="onView">
              <EyeOutlined /> 查看详情
            </a-button>
          </a-tooltip>
        </a-space>
      </template>
      <a-table
        v-if="materials.length > 0 || loading"
        :data-source="materials"
        :loading="loading"
        :pagination="{ pageSize: 10, showTotal: (t) => `共 ${t} 条`, showSizeChanger: true, pageSizeOptions: ['10', '20', '50'] }"
        :columns="columns"
        size="middle"
        :row-key="(r) => r.material_id"
        :row-class-name="(record) => (record.is_toxic ? 'toxic-row' : '')"
        :row-selection="{ selectedRowKeys: selectedRowKeys, onChange: onSelectChange, type: 'radio' }"
        :scroll="{ x: 890 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'molecule'">
            <MoleculeView :smiles="record.smiles" :size="120" />
          </template>
          <template v-else-if="column.key === 'material_id'">
            <span class="mat-id">{{ record.material_id }}</span>
          </template>
          <template v-else-if="column.key === 'category'">
            <a-tag :color="categoryColor(record.category)">{{ categoryLabel(record.category) }}</a-tag>
          </template>
          <template v-else-if="column.key === 'inventory_kg'">
            <span class="num">{{ record.inventory_kg }} {{ record.inventory_unit || massUnit }}</span>
          </template>
          <template v-else-if="column.key === 'unit_cost'">
            <span class="num cost">¥{{ (record.unit_cost || 0).toFixed(1) }}/{{ record.inventory_unit || massUnit }}</span>
          </template>
          <template v-else-if="column.key === 'reach_compliant'">
            <!-- Task 13：合规字段必须有凭证支撑，无凭证显示"待补充证据" -->
            <template v-if="record.reach_compliant && hasEvidence(record)">
              <a-tag color="#10b981">合规</a-tag>
              <div class="evidence-link-row">
                <a v-if="record.coa_uri" :href="record.coa_uri" target="_blank" class="evidence-link">COA</a>
                <a v-if="record.sds_uri" :href="record.sds_uri" target="_blank" class="evidence-link">SDS</a>
                <a v-if="record.test_report_uri" :href="record.test_report_uri" target="_blank" class="evidence-link">报告</a>
              </div>
            </template>
            <template v-else-if="record.reach_compliant && !hasEvidence(record)">
              <a-tag color="#f59e0b">待补充证据</a-tag>
              <div class="evidence-link-row">
                <a-button size="small" type="link" class="upload-btn" @click="onUploadEvidence(record)">
                  <UploadOutlined /> 上传报告
                </a-button>
              </div>
            </template>
            <template v-else>
              <a-tag color="#ef4444">不合规</a-tag>
            </template>
          </template>
          <template v-else-if="column.key === 'is_toxic'">
            <a-tag v-if="record.is_toxic" color="#ef4444" class="toxic-tag">
              <WarningOutlined aria-hidden="true" /> 有毒/高危
            </a-tag>
            <a-tag v-else color="#64748b">无毒</a-tag>
          </template>
          <template v-else-if="column.key === 'batch'">
            <span>{{ record.batch_number || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'expiry'">
            <span>{{ record.expiry_date || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'coa'">
            <a v-if="record.coa_uri" :href="record.coa_uri" target="_blank">查看</a>
            <span v-else>-</span>
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="onViewRow(record)">详情</a-button>
              <a-button type="link" size="small" @click="onEditRow(record)">编辑</a-button>
            </a-space>
          </template>
        </template>
      </a-table>
      <div v-else class="empty-state">
        <EmptyState type="create" description="暂无物料数据" action-text="新增物料" secondary-text="刷新" @action="onAdd" @secondary="onQuery" />
      </div>
    </a-card>

    <!-- 新增/编辑物料抽屉 -->
    <a-drawer
      :open="formModalVisible"
      :title="formMode === 'create' ? '新增物料规格' : `编辑物料 ${form.material_id}`"
      placement="right"
      width="720px"
      @update:open="(v) => (formModalVisible = v)"
    >
      <a-form ref="formRef" class="compact-form" layout="vertical" size="small" :model="form" :rules="formRules">
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="物料编码" name="material_id">
              <a-input
                v-model:value="form.material_id"
                name="material_id"
                :disabled="formMode === 'edit'"
                placeholder="留空自动生成 RM-xxx"
                autocomplete="off"
                :spellcheck="false"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="名称" name="name" required>
              <a-input v-model:value="form.name" name="name" autocomplete="off" placeholder="如 PEO…" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="分类" name="category" required>
              <a-select v-model:value="form.category" name="category" :options="categoryOptions" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item label="SMILES">
              <div style="display: flex; gap: 8px;">
                <a-input v-model:value="form.smiles" name="smiles" placeholder="分子结构 SMILES 表达式…" :spellcheck="false" style="flex: 1" />
                <a-button size="small" @click="onGenerateSmiles" :loading="smilesLoading">AI 生成</a-button>
              </div>
            </a-form-item>
          </a-col>
        </a-row>

        <!-- 按属性字典模板动态加载的属性字段（按字典类型分组） -->
        <a-divider v-if="templateFields.length" orientation="left" style="font-size: 12px; color: var(--text-secondary)">
          类型属性（按属性字典模板）
        </a-divider>
        <a-spin :spinning="templateLoading">
          <EmptyState
            v-if="!templateLoading && form.category && templateFields.length === 0"
            type="data"
            description="当前物料类型未配置属性模板，请前往「属性字典」页面设置"
          />
          <div v-for="group in templateFieldGroups" :key="group.key" class="dict-group">
            <div class="dict-group-title">{{ group.label_cn }}</div>
            <a-row :gutter="16">
              <a-col
                v-for="field in group.fields"
                :key="field.key"
                :span="field.value_type === 'str' || field.value_type === 'dict' || field.value_type === 'list' ? 12 : 8"
              >
                <a-form-item :label="propertyLabel(field)">
                  <a-input-number
                    v-if="field.value_type === 'float' || field.value_type === 'int'"
                    v-model:value="form.properties[field.key]"
                    :min="field.value_type === 'int' ? -2147483648 : undefined"
                    :step="field.value_type === 'int' ? 1 : 0.1"
                    style="width: 100%"
                    :placeholder="`输入 ${field.label_cn}`"
                  />
                  <a-textarea
                    v-else-if="field.value_type === 'dict' || field.value_type === 'list'"
                    v-model:value="form.properties[field.key]"
                    :rows="2"
                    :placeholder="`输入 ${field.label_cn}，JSON 格式`"
                  />
                  <a-input
                    v-else
                    v-model:value="form.properties[field.key]"
                    :placeholder="`输入 ${field.label_cn}`"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </div>
        </a-spin>

        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item :label="`库存 (${massUnit})`" name="inventory_kg">
              <a-input-number v-model:value="form.inventory_kg" name="inventory_kg" :min="0" :step="1" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item :label="`单价 (元/${massUnit})`" name="unit_cost">
              <a-input-number v-model:value="form.unit_cost" name="unit_cost" :min="0" :step="10" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item :label="`最小起订量 (${massUnit})`" name="min_order_quantity">
              <a-input-number v-model:value="form.min_order_quantity" name="min_order_quantity" :min="0" :step="1" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="供应商" name="supplier">
              <a-input v-model:value="form.supplier" name="supplier" autocomplete="off" placeholder="如 国药集团…" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="批次号" name="batch_number">
              <a-input v-model:value="form.batch_number" name="batch_number" autocomplete="off" :spellcheck="false" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="有效期">
              <a-date-picker v-model:value="form.expiry_date" name="expiry_date" style="width: 100%" value-format="YYYY-MM-DD" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item label="COA 链接" name="coa_uri">
              <a-input v-model:value="form.coa_uri" name="coa_uri" placeholder="https://…" autocomplete="off" :spellcheck="false" />
            </a-form-item>
          </a-col>
        </a-row>
        <!-- Task 13：合规证据字段 —— REACH/SDS/毒性合规声明必须有凭证支撑 -->
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item label="SDS 报告链接" name="sds_uri">
              <a-input v-model:value="form.sds_uri" name="sds_uri" placeholder="https://…" autocomplete="off" :spellcheck="false" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item label="第三方检测报告链接" name="test_report_uri">
              <a-input v-model:value="form.test_report_uri" name="test_report_uri" placeholder="https://…" autocomplete="off" :spellcheck="false" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="检测机构">
              <a-input v-model:value="form.test_institution" name="test_institution" autocomplete="off" placeholder="如 SGS、国检中心…" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="检测日期">
              <a-date-picker v-model:value="form.test_date" name="test_date" style="width: 100%" value-format="YYYY-MM-DD" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="REACH 合规">
              <a-switch v-model:checked="form.reach_compliant" />
              <span class="form-hint-inline">未合规物料无法通过配方合规检查</span>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="毒性/高危">
              <a-switch v-model:checked="form.is_toxic" />
              <span class="form-hint-inline">标记后将升级 EHS 防护等级</span>
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="formSubmitting" @click="formModalVisible = false">取消</a-button>
          <a-button type="primary" :loading="formSubmitting" @click="onSubmitForm">保存</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 物料详情抽屉（含版本历史） -->
    <a-drawer
      :open="detailModalVisible"
      :title="`物料详情 ${detailMaterial?.material_id || ''}`"
      placement="right"
      width="900px"
      :footer="null"
      @update:open="onDetailDrawerClose"
    >
      <a-tabs v-model:activeKey="detailTab">
        <!-- 基本信息 -->
        <a-tab-pane key="info" tab="基本信息">
          <a-descriptions v-if="detailMaterial" :column="2" bordered size="small">
            <a-descriptions-item label="物料编码">{{ detailMaterial.material_id }}</a-descriptions-item>
            <a-descriptions-item label="名称">{{ detailMaterial.name || '-' }}</a-descriptions-item>
            <a-descriptions-item label="分类">
              <a-tag :color="categoryColor(detailMaterial.category)">{{ categoryLabel(detailMaterial.category) }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="SMILES">
              <span class="smiles-text">{{ detailMaterial.smiles || '-' }}</span>
            </a-descriptions-item>
            <a-descriptions-item label="库存">{{ detailMaterial.inventory_kg }} {{ detailMaterial.inventory_unit || massUnit }}</a-descriptions-item>
            <a-descriptions-item label="单价">¥{{ (detailMaterial.unit_cost || 0).toFixed(1) }}/{{ detailMaterial.inventory_unit || massUnit }}</a-descriptions-item>
            <a-descriptions-item label="最小起订量">{{ detailMaterial.min_order_quantity || 0 }} {{ detailMaterial.inventory_unit || massUnit }}</a-descriptions-item>
            <a-descriptions-item label="供应商">{{ detailMaterial.supplier || '-' }}</a-descriptions-item>
            <a-descriptions-item label="批次号">{{ detailMaterial.batch_number || '-' }}</a-descriptions-item>
            <a-descriptions-item label="有效期">{{ detailMaterial.expiry_date || '-' }}</a-descriptions-item>
            <a-descriptions-item label="版本">v{{ detailMaterial.version || 1 }}</a-descriptions-item>
            <a-descriptions-item label="更新人">{{ detailMaterial.updated_by || '-' }}</a-descriptions-item>
            <a-descriptions-item label="数据来源" :span="2">
              <a-tooltip v-if="detailMaterial.data_source === 'predicted' && detailMaterial.prediction_meta">
                <template #title>
                  <div>模型：{{ detailMaterial.prediction_meta.model || '-' }}</div>
                  <div>置信度：{{ detailMaterial.prediction_meta.confidence != null ? (detailMaterial.prediction_meta.confidence * 100).toFixed(1) + '%' : '-' }}</div>
                  <div v-if="detailMaterial.prediction_meta.predicted_property">预测属性：{{ detailMaterial.prediction_meta.predicted_property }}</div>
                  <div v-if="detailMaterial.prediction_meta.predicted_value != null">预测值：{{ detailMaterial.prediction_meta.predicted_value }}</div>
                </template>
                <a-tag color="blue" class="source-tag">预测值</a-tag>
              </a-tooltip>
              <a-tag v-else color="green" class="source-tag">实测值</a-tag>
            </a-descriptions-item>
          </a-descriptions>

          <!-- REACH 合规检查（AI Agent 处理） -->
          <div v-if="detailMaterial" class="compliance-section">
            <div class="compliance-header">
              <span class="compliance-title">REACH 合规检查</span>
              <a-tag color="purple" class="agent-tag">
                <RobotOutlined /> AI 合规检查
              </a-tag>
            </div>
            <a-descriptions :column="2" bordered size="small">
              <a-descriptions-item label="合规状态">
                <a-tag v-if="complianceStatus(detailMaterial) === 'compliant'" color="#10b981">合规</a-tag>
                <a-tag v-else-if="complianceStatus(detailMaterial) === 'pending_evidence'" color="#f59e0b">待补充证据</a-tag>
                <a-tag v-else color="#ef4444">不合规</a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="毒性">
                <a-tag v-if="detailMaterial.is_toxic" color="#ef4444">有毒/高危</a-tag>
                <a-tag v-else color="#64748b">无毒</a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="检测机构">{{ detailMaterial.test_institution || '-' }}</a-descriptions-item>
              <a-descriptions-item label="检测日期">{{ detailMaterial.test_date || '-' }}</a-descriptions-item>
              <a-descriptions-item label="合规证据" :span="2">
                <div v-if="evidenceLinks(detailMaterial).length > 0" class="evidence-detail-list">
                  <a v-for="ev in evidenceLinks(detailMaterial)" :key="ev.label" :href="ev.uri" target="_blank" class="evidence-link">
                    <FileAddOutlined /> {{ ev.label }}
                  </a>
                </div>
                <span v-else class="evidence-empty">
                  未关联检测报告凭证
                  <a-button size="small" type="link" @click="onUploadEvidence(detailMaterial)">
                    <UploadOutlined /> 上传报告
                  </a-button>
                </span>
              </a-descriptions-item>
            </a-descriptions>
          </div>

          <!-- 物料申请入口 -->
          <div class="request-actions">
            <a-space>
              <a-button type="primary" size="small" @click="onRequestNew">
                <FileAddOutlined /> 申请新物料
              </a-button>
              <a-button size="small" @click="onRequestModify">
                <EditOutlined /> 申请修改
              </a-button>
            </a-space>
          </div>
        </a-tab-pane>

        <!-- 按字典类型分组的属性字段 Tab（每个字典类型一个 Tab） -->
        <a-tab-pane
          v-for="group in detailPropertyGroups"
          :key="`dict_${group.key}`"
          :tab="`${group.label_cn}`"
        >
          <a-descriptions :column="2" bordered size="small">
            <a-descriptions-item
              v-for="field in group.fields"
              :key="field.key"
              :label="propertyLabel(field)"
            >
              <span v-if="!isEmptyPropertyValue(detailMaterial?.properties?.[field.key])" class="num">
                {{ detailMaterial.properties[field.key] }}
              </span>
              <span v-else class="text-muted">-</span>
            </a-descriptions-item>
          </a-descriptions>
          <EmptyState
            v-if="group.fields.length === 0"
            type="data"
            description="该字典类型暂无属性字段"
          />
        </a-tab-pane>

        <!-- 版本历史 -->
        <a-tab-pane key="versions" tab="版本历史">
          <div class="version-toolbar">
            <a-space>
              <a-button size="small" type="primary" :loading="versionSaving" @click="onSaveSnapshot">
                <SaveOutlined /> 保存当前为快照
              </a-button>
              <a-button size="small" :loading="versionLoading" @click="fetchVersions">
                <HistoryOutlined /> 刷新
              </a-button>
            </a-space>
            <span class="version-hint">共 {{ versions.length }} 个版本</span>
          </div>

          <div v-if="versions.length === 0 && !versionLoading" class="empty-state" style="padding: 24px">
            暂无版本记录，点击「保存当前为快照」创建首个版本
          </div>

          <a-list v-else :data-source="versions" :loading="versionLoading" size="small">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-list-item-meta>
                  <template #title>
                    <span class="version-title">
                      <span class="version-number">v{{ item.version_number }}</span>
                      <a-tag v-if="item.is_active" color="#10b981" class="active-tag">
                        <CheckCircleOutlined aria-hidden="true" /> 活跃
                      </a-tag>
                    </span>
                  </template>
                  <template #description>
                    <div class="version-desc">
                      <div>{{ item.change_summary || '（无变更说明）' }}</div>
                      <div class="version-meta">
                        <span>{{ item.created_by || 'system' }}</span>
                        <span>{{ formatTime(item.created_at) }}</span>
                      </div>
                    </div>
                  </template>
                </a-list-item-meta>
                <template #actions>
                  <a-space size="small">
                    <a-button
                      size="small"
                      :type="expandedVersionId === item.version_id ? 'primary' : 'default'"
                      @click="toggleSnapshot(item)"
                    >
                      {{ expandedVersionId === item.version_id ? '收起' : '查看快照' }}
                    </a-button>
                    <a-button
                      v-if="!item.is_active"
                      size="small"
                      :loading="activatingId === item.version_id"
                      @click="onActivate(item)"
                    >
                      设为活跃
                    </a-button>
                    <a-button
                      size="small"
                      :loading="reusingId === item.version_id"
                      @click="onReuse(item)"
                    >
                      <CopyOutlined /> 复用此版本
                    </a-button>
                  </a-space>
                </template>
              </a-list-item>
            </template>
          </a-list>

          <!-- 快照展开 -->
          <a-card
            v-if="expandedVersion"
            class="snapshot-card"
            :bordered="true"
            size="small"
            :title="`快照详情 v${expandedVersion.version_number}`"
          >
            <pre class="snapshot-json">{{ JSON.stringify(expandedVersion.snapshot, null, 2) }}</pre>
          </a-card>
        </a-tab-pane>
      </a-tabs>
    </a-drawer>

    <!-- 物料申请抽屉 -->
    <a-drawer
      :open="requestModalVisible"
      :title="requestForm.request_type === 'add' ? '申请新物料' : `申请修改 ${requestForm.material_id}`"
      placement="right"
      width="720px"
      @update:open="(v) => (requestModalVisible = v)"
    >
      <a-alert
        type="info"
        show-icon
        message="物料申请提交后需经审批通过才会写入物料库"
        style="margin-bottom: 12px"
      />
      <a-form class="compact-form" layout="vertical" size="small">
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="物料编码">
              <a-input
                v-model:value="requestForm.material_id"
                name="material_id"
                :disabled="requestForm.request_type === 'update'"
                placeholder="留空自动生成 RM-xxx"
                autocomplete="off"
                :spellcheck="false"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="名称" required>
              <a-input v-model:value="requestForm.name" name="name" autocomplete="off" placeholder="如 PEO…" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="分类" required>
              <a-select v-model:value="requestForm.category" name="category" :options="categoryOptions" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item label="SMILES">
              <a-input v-model:value="requestForm.smiles" name="smiles" placeholder="分子结构 SMILES 表达式…" :spellcheck="false" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item :label="`库存 (${massUnit})`">
              <a-input-number v-model:value="requestForm.inventory_kg" name="inventory_kg" :min="0" :step="1" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item :label="`单价 (元/${massUnit})`">
              <a-input-number v-model:value="requestForm.unit_cost" name="unit_cost" :min="0" :step="10" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item :label="`最小起订量 (${massUnit})`">
              <a-input-number v-model:value="requestForm.min_order_quantity" name="min_order_quantity" :min="0" :step="1" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item label="供应商">
              <a-input v-model:value="requestForm.supplier" name="supplier" autocomplete="off" placeholder="如 国药集团…" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="REACH 合规">
              <a-switch v-model:checked="requestForm.reach_compliant" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="毒性/高危">
              <a-switch v-model:checked="requestForm.is_toxic" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="申请原因" required>
              <a-input v-model:value="requestForm.update_reason" name="update_reason" placeholder="说明申请此物料变更的原因…" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="申请人">
              <a-input v-model:value="requestForm.requester" name="requester" autocomplete="off" placeholder="留空使用当前登录用户" />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
      <template #footer>
        <a-space style="display: flex; justify-content: flex-end">
          <a-button :disabled="requestSubmitting" @click="requestModalVisible = false">取消</a-button>
          <a-button type="primary" :loading="requestSubmitting" @click="onSubmitRequest">保存</a-button>
        </a-space>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  SearchOutlined, WarningOutlined, PlusOutlined, EditOutlined,
  EyeOutlined, HistoryOutlined, SaveOutlined, CopyOutlined, CheckCircleOutlined,
  FileAddOutlined, UploadOutlined, ReloadOutlined, RobotOutlined,
} from '@ant-design/icons-vue'
import { getRawMaterials, createRawMaterial, updateRawMaterial } from '@/api/rawMaterials'
import {
  getMaterialTypeTemplate,
  getCategories,
} from '@/api/properties'
import { listVersions, createVersion, activateVersion } from '@/api/versions'
import { createMaterialRequest } from '@/api/materialRequests'
import client from '@/api/client'
import { message } from 'ant-design-vue'
import MoleculeView from '@/components/MoleculeView.vue'
import EmptyState from '@/components/EmptyState.vue'
import {
  DEFAULT_INDUSTRIAL_CATEGORIES,
  industrialCategoryLabel,
  industrialCategoryColor,
} from '@/constants/materialTypes'
import { useMdmDict, useUnitSymbols } from '@/utils/mdmDict'

const materials = ref([])
const loading = ref(false)
const filterCategory = ref(undefined)
const route = useRoute()

const { classificationOptions: mdmClassificationOptions } = useMdmDict()
const { symbols: unitSymbols, load: loadUnitSymbols } = useUnitSymbols()
const massUnit = computed(() => unitSymbols.value.mass || 'kg')

// 行选择（单选模式，用于编辑）
const selectedRowKeys = ref([])
const selectedMaterial = ref(null)

// 新增/编辑表单
const formModalVisible = ref(false)
const formSubmitting = ref(false)
const smilesLoading = ref(false)
const formMode = ref('create')  // 'create' | 'edit'
const emptyForm = () => ({
  material_id: '',
  name: '',
  smiles: '',
  category: 'BASE_POLYMER',
  inventory_kg: 0,
  unit_cost: 0,
  supplier: '',
  reach_compliant: true,
  is_toxic: false,
  batch_number: '',
  expiry_date: '',
  coa_uri: '',
  // Task 13：合规证据字段
  sds_uri: '',
  test_report_uri: '',
  test_institution: '',
  test_date: '',
  min_order_quantity: 0,
  properties: {},
})
const form = ref(emptyForm())

// P1-FORM-001：新建/编辑物料表单校验（名称必填，关键字段长度/格式/范围校验）
const formRef = ref(null)
const formRules = {
  name: [
    { required: true, message: '请输入名称' },
    {
      validator: async (rule, value) => {
        if (!value || value.trim().length < 2) throw new Error('名称至少 2 个字符')
        // 仅在创建模式或名称变更时检查重复
        if (formMode.value === 'create') {
          const exists = materials.value.some(m => m.name === value.trim())
          if (exists) throw new Error('该名称已存在，请使用不同名称')
        }
      },
      trigger: 'blur',
    },
  ],
  category: [{ required: true, message: '请选择物料分类', trigger: 'change' }],
  material_id: [{ max: 64, message: '物料编码不能超过 64 个字符', trigger: 'blur' }],
  supplier: [{ max: 100, message: '供应商名称不能超过 100 个字符', trigger: 'blur' }],
  batch_number: [{ max: 64, message: '批次号不能超过 64 个字符', trigger: 'blur' }],
  inventory_kg: [
    {
      validator: (_rule, value) => {
        if (value === null || value === undefined || value === '') return Promise.resolve()
        const num = Number(value)
        if (Number.isNaN(num)) return Promise.reject('请输入有效数值')
        if (num < 0) return Promise.reject('库存量不能为负数')
        return Promise.resolve()
      },
      trigger: 'blur',
    },
  ],
  unit_cost: [
    {
      validator: (_rule, value) => {
        if (value === null || value === undefined || value === '') return Promise.resolve()
        const num = Number(value)
        if (Number.isNaN(num)) return Promise.reject('请输入有效数值')
        if (num < 0) return Promise.reject('单价不能为负数')
        return Promise.resolve()
      },
      trigger: 'blur',
    },
  ],
  min_order_quantity: [
    {
      validator: (_rule, value) => {
        if (value === null || value === undefined || value === '') return Promise.resolve()
        const num = Number(value)
        if (Number.isNaN(num)) return Promise.reject('请输入有效数值')
        if (num < 0) return Promise.reject('最小起订量不能为负数')
        return Promise.resolve()
      },
      trigger: 'blur',
    },
  ],
  coa_uri: [
    {
      validator: (_rule, value) => {
        if (!value) return Promise.resolve()
        try {
          new URL(value)
          return Promise.resolve()
        } catch {
          return Promise.reject('请输入有效的 URL')
        }
      },
      trigger: 'blur',
    },
  ],
  sds_uri: [
    {
      validator: (_rule, value) => {
        if (!value) return Promise.resolve()
        try {
          new URL(value)
          return Promise.resolve()
        } catch {
          return Promise.reject('请输入有效的 URL')
        }
      },
      trigger: 'blur',
    },
  ],
  test_report_uri: [
    {
      validator: (_rule, value) => {
        if (!value) return Promise.resolve()
        try {
          new URL(value)
          return Promise.resolve()
        } catch {
          return Promise.reject('请输入有效的 URL')
        }
      },
      trigger: 'blur',
    },
  ],
}

// 按物料类型模板动态加载的属性字段
const templateFields = ref([])
const templateLoading = ref(false)
// 所有字典类型（属性类别），用于按字典类型分组展示
const propertyCategories = ref([])

// 表单中按字典类型分组的模板字段（便于分组展示）
const templateFieldGroups = computed(() => {
  if (templateFields.value.length === 0) return []
  const groups = []
  for (const cat of propertyCategories.value) {
    const fields = templateFields.value.filter((f) =>
      (cat.fields || []).some((cf) => cf.key === f.key)
    )
    if (fields.length > 0) {
      groups.push({ key: cat.key, label_cn: cat.label_cn, icon: cat.icon, fields })
    }
  }
  return groups
})

// 物料详情中按字典类型分组的模板字段
const detailTemplateFields = ref([])
const detailPropertyGroups = computed(() => {
  if (detailTemplateFields.value.length === 0) return []
  const groups = []
  for (const cat of propertyCategories.value) {
    const fields = detailTemplateFields.value.filter((f) =>
      (cat.fields || []).some((cf) => cf.key === f.key)
    )
    if (fields.length > 0) {
      groups.push({ key: cat.key, label_cn: cat.label_cn, icon: cat.icon, fields })
    }
  }
  return groups
})

// 物料分类下拉：默认硬编码兜底，onMounted 时尝试从 MDM 动态获取
const categoryOptions = ref([...DEFAULT_INDUSTRIAL_CATEGORIES])

// P2-1：精简表格列，次要信息（最小起订量、REACH、毒性、版本、更新人）移至详情抽屉
// P3-7：移除独立 SMILES 列（分子图谱已可视化展示），合并批次/有效期，压缩总宽至 ~880px
const columns = [
  { title: '物料编码', key: 'material_id', dataIndex: 'material_id', width: 90, className: 'id-col' },
  { title: '名称', dataIndex: 'name', key: 'name', width: 100, ellipsis: true },
  { title: '分子图谱', key: 'molecule', width: 110 },
  { title: '分类', key: 'category', width: 80 },
  { title: '库存', key: 'inventory_kg', width: 80, className: 'tabular-nums' },
  { title: '单价', key: 'unit_cost', width: 80, className: 'tabular-nums' },
  { title: '供应商', dataIndex: 'supplier', key: 'supplier', width: 80, ellipsis: true },
  { title: '批次/有效期', key: 'batch_expiry', width: 110, ellipsis: true },
  { title: 'COA', dataIndex: 'coa_uri', key: 'coa', width: 60 },
  { title: '操作', key: 'action', width: 100, fixed: 'right' },
]

const totalCost = computed(() => {
  if (materials.value.length === 0) return 0
  const sum = materials.value.reduce((s, m) => s + (m.unit_cost || 0), 0)
  return sum / materials.value.length
})

// Task 13：仅统计有证据支撑的合规物料（声明合规 + 关联检测报告）
const reachCompliantCount = computed(
  () => materials.value.filter((m) => m.reach_compliant && hasEvidence(m)).length
)
const toxicCount = computed(() => materials.value.filter((m) => m.is_toxic).length)

function formatCost(v) {
  return (v || 0).toFixed(1)
}

// 物料分类标签/颜色：统一引用 constants/materialTypes 中的工具函数
function categoryLabel(cat) {
  return industrialCategoryLabel(cat, categoryOptions.value)
}

function categoryColor(cat) {
  const raw = industrialCategoryColor(cat, categoryOptions.value)
  const statusColorMap = {
    purple: '#8b5cf6',
    blue: '#3b82f6',
    green: '#10b981',
    orange: '#f59e0b',
    red: '#ef4444',
    default: '#64748b',
  }
  return statusColorMap[raw] || raw
}

// 加载物料类型属性模板
async function loadMaterialTemplate(category) {
  templateFields.value = []
  if (!category) return
  templateLoading.value = true
  try {
    const res = await getMaterialTypeTemplate(category)
    templateFields.value = res?.fields || []
  } catch {
    templateFields.value = []
  } finally {
    templateLoading.value = false
  }
}

async function loadPropertyFieldMap() {
  try {
    const res = await getCategories()
    const cats = res?.categories || []
    propertyCategories.value = cats
  } catch {
    propertyCategories.value = []
  }
}

// 加载物料详情中按字典类型分组的模板字段
async function loadTemplateForDetail(category) {
  detailTemplateFields.value = []
  if (!category) return
  try {
    const res = await getMaterialTypeTemplate(category)
    detailTemplateFields.value = res?.fields || []
  } catch {
    detailTemplateFields.value = []
  }
}

// 动态属性字段占位（用于中文标签展示）
function propertyLabel(field) {
  return `${field.label_cn}${field.unit ? ` (${field.unit})` : ''}`
}

// 判断属性值是否为空
function isEmptyPropertyValue(v) {
  return v === undefined || v === null || v === ''
}

// 当表单分类变化时，自动加载对应物料类型的属性模板
watch(() => form.value.category, (cat) => {
  if (cat) {
    loadMaterialTemplate(cat)
    // 切换类型时保留已有属性值，但确保 properties 对象存在
    if (!form.value.properties) form.value.properties = {}
  }
})

// Task 13：合规证据判定 —— 声明合规必须有 COA/SDS/第三方检测报告任一凭证
function hasEvidence(record) {
  return Boolean(
    (record.coa_uri && record.coa_uri.trim()) ||
    (record.sds_uri && record.sds_uri.trim()) ||
    (record.test_report_uri && record.test_report_uri.trim())
  )
}

// 返回物料的合规状态：compliant / pending_evidence / non_compliant
function complianceStatus(record) {
  if (!record.reach_compliant) return 'non_compliant'
  return hasEvidence(record) ? 'compliant' : 'pending_evidence'
}

// 收集物料的合规证据链接列表（用于详情展示）
function evidenceLinks(record) {
  const links = []
  if (record.coa_uri) links.push({ label: 'COA 报告', uri: record.coa_uri })
  if (record.sds_uri) links.push({ label: 'SDS 报告', uri: record.sds_uri })
  if (record.test_report_uri) links.push({ label: '检测报告', uri: record.test_report_uri })
  return links
}

async function onQuery() {
  loading.value = true
  try {
    const data = await getRawMaterials(filterCategory.value || '')
    materials.value = data.materials || []
  } catch (e) {
    message.error('物料查询失败')
    materials.value = []
  } finally {
    loading.value = false
  }
}

function onSelectChange(keys, rows) {
  selectedRowKeys.value = keys
  selectedMaterial.value = rows[0] || null
}

function onAdd() {
  formMode.value = 'create'
  form.value = emptyForm()
  formRef.value?.clearValidate()
  loadMaterialTemplate(form.value.category)
  formModalVisible.value = true
}

function onEdit() {
  if (!selectedMaterial.value) {
    message.warning('请先选择一行物料')
    return
  }
  onEditRow(selectedMaterial.value)
}

function onEditRow(record) {
  selectedRowKeys.value = [record.material_id]
  selectedMaterial.value = record
  formMode.value = 'edit'
  form.value = { ...emptyForm(), ...record }
  if (!form.value.properties) form.value.properties = {}
  formRef.value?.clearValidate()
  loadMaterialTemplate(form.value.category)
  formModalVisible.value = true
}

// Task 13：从"待补充证据"徽章入口直接打开编辑弹窗，聚焦合规证据上传
function onUploadEvidence(record) {
  selectedRowKeys.value = [record.material_id]
  selectedMaterial.value = record
  formMode.value = 'edit'
  form.value = { ...emptyForm(), ...record }
  formRef.value?.clearValidate()
  formModalVisible.value = true
  message.info('请在"合规证据"区域上传 COA / SDS / 检测报告链接')
}

async function onSubmitForm() {
  // P1-3：提交前表单校验，校验失败不提交
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  formSubmitting.value = true
  try {
    if (formMode.value === 'create') {
      await createRawMaterial(form.value)
      message.success('物料已新增')
    } else {
      await updateRawMaterial(form.value.material_id, form.value)
      message.success('物料已更新')
    }
    formModalVisible.value = false
    selectedRowKeys.value = []
    selectedMaterial.value = null
    await onQuery()
  } catch {
    // 错误由拦截器处理
  } finally {
    formSubmitting.value = false
  }
}

// 调用 SCP NameToSMILES 工具，根据物料名称生成 SMILES
async function onGenerateSmiles() {
  if (!form.value.name?.trim()) {
    message.warning('请先填写物料名称')
    return
  }
  smilesLoading.value = true
  try {
    const res = await client.post('/scp/tools/NameToSMILES', { name: form.value.name }, { skipErrorNotification: true })
    const smiles = typeof res === 'string'
      ? res
      : (res?.smiles || res?.result || res?.output || '')
    if (smiles && typeof smiles === 'string') {
      form.value.smiles = smiles.trim()
      message.success('SMILES 生成成功')
    } else {
      message.warning('未获取到 SMILES 结果')
    }
  } catch (e) {
    message.error('SMILES 生成失败')
  } finally {
    smilesLoading.value = false
  }
}

// --- 物料详情弹窗 + 版本历史 ---

const detailModalVisible = ref(false)
const detailMaterial = ref(null)
const detailTab = ref('info')

// 版本列表
const versions = ref([])
const versionLoading = ref(false)
const versionSaving = ref(false)
const expandedVersionId = ref('')
const expandedVersion = ref(null)
const activatingId = ref('')
const reusingId = ref('')

function onView() {
  if (!selectedMaterial.value) {
    message.warning('请先选择一行物料')
    return
  }
  onViewRow(selectedMaterial.value)
}

function onViewRow(record) {
  selectedRowKeys.value = [record.material_id]
  selectedMaterial.value = record
  detailMaterial.value = { ...record }
  detailTab.value = 'info'
  expandedVersionId.value = ''
  expandedVersion.value = null
  versions.value = []
  detailModalVisible.value = true
  fetchVersions()
  // 加载该物料分类对应的属性模板字段，用于详情中按字典类型分组展示
  loadTemplateForDetail(detailMaterial.value.category)
}

function onDetailDrawerClose(v) {
  detailModalVisible.value = v
  if (!v) {
    detailMaterial.value = null
    versions.value = []
    expandedVersionId.value = ''
    expandedVersion.value = null
  }
}

async function fetchVersions() {
  if (!detailMaterial.value) return
  versionLoading.value = true
  try {
    const data = await listVersions('material', detailMaterial.value.material_id)
    versions.value = data.versions || []
  } catch {
    versions.value = []
  } finally {
    versionLoading.value = false
  }
}

function toggleSnapshot(item) {
  if (expandedVersionId.value === item.version_id) {
    expandedVersionId.value = ''
    expandedVersion.value = null
  } else {
    expandedVersionId.value = item.version_id
    expandedVersion.value = item
  }
}

async function onSaveSnapshot() {
  if (!detailMaterial.value) return
  versionSaving.value = true
  try {
    await createVersion({
      entity_type: 'material',
      entity_id: detailMaterial.value.material_id,
      snapshot: { ...detailMaterial.value },
      change_summary: '人工保存当前物料快照',
      created_by: localStorage.getItem('userId') || 'system',
      is_active: true,
    })
    message.success('快照已保存')
    await fetchVersions()
  } catch {
    // 错误由拦截器处理
  } finally {
    versionSaving.value = false
  }
}

async function onActivate(item) {
  activatingId.value = item.version_id
  try {
    await activateVersion(item.version_id)
    message.success(`v${item.version_number} 已设为活跃版本`)
    await fetchVersions()
  } catch {
    // 错误由拦截器处理
  } finally {
    activatingId.value = ''
  }
}

async function onReuse(item) {
  // 基于历史版本快照创建新版本
  reusingId.value = item.version_id
  try {
    await createVersion({
      entity_type: 'material',
      entity_id: item.entity_id,
      snapshot: { ...(item.snapshot || {}) },
      change_summary: `复用 v${item.version_number} 快照创建新版本`,
      created_by: localStorage.getItem('userId') || 'system',
      is_active: false,
    })
    message.success(`已基于 v${item.version_number} 创建新版本`)
    await fetchVersions()
  } catch {
    // 错误由拦截器处理
  } finally {
    reusingId.value = ''
  }
}

function formatTime(s) {
  if (!s) return ''
  try {
    return new Date(s).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return s
  }
}

// --- 物料申请 ---

const requestModalVisible = ref(false)
const requestSubmitting = ref(false)
const emptyRequestForm = () => ({
  request_type: 'add',
  material_id: '',
  name: '',
  smiles: '',
  category: 'BASE_POLYMER',
  inventory_kg: 0,
  unit_cost: 0,
  supplier: '',
  reach_compliant: true,
  is_toxic: false,
  min_order_quantity: 0,
  update_reason: '',
  requester: '',
})
const requestForm = ref(emptyRequestForm())

function onRequestNew() {
  requestForm.value = { ...emptyRequestForm(), request_type: 'add' }
  requestModalVisible.value = true
}

function onRequestModify() {
  if (!detailMaterial.value) return
  requestForm.value = {
    ...emptyRequestForm(),
    request_type: 'update',
    material_id: detailMaterial.value.material_id,
    name: detailMaterial.value.name || '',
    smiles: detailMaterial.value.smiles || '',
    category: detailMaterial.value.category || 'BASE_POLYMER',
    inventory_kg: detailMaterial.value.inventory_kg || 0,
    unit_cost: detailMaterial.value.unit_cost || 0,
    supplier: detailMaterial.value.supplier || '',
    reach_compliant: detailMaterial.value.reach_compliant ?? true,
    is_toxic: detailMaterial.value.is_toxic ?? false,
    min_order_quantity: detailMaterial.value.min_order_quantity || 0,
  }
  requestModalVisible.value = true
}

async function onSubmitRequest() {
  if (!requestForm.value.name?.trim()) {
    message.warning('请填写物料名称')
    return
  }
  if (!requestForm.value.update_reason?.trim()) {
    message.warning('请填写申请原因')
    return
  }
  requestSubmitting.value = true
  try {
    const { request_type, update_reason, requester, ...materialFields } = requestForm.value
    await createMaterialRequest({
      material_data: {
        ...materialFields,
        update_reason,
        data_source: materialFields.data_source || 'measured',
      },
      request_type,
      requester: requester || localStorage.getItem('userId') || '',
    })
    message.success('物料申请已提交，等待审批')
    requestModalVisible.value = false
  } catch {
    // 错误由拦截器处理
  } finally {
    requestSubmitting.value = false
  }
}

onMounted(async () => {
  loadPropertyFieldMap()
  loadUnitSymbols()
  onQuery()
  // 从 MDM 加载物料分类选项（失败则保留硬编码兜底）
  try {
    const opts = await mdmClassificationOptions('material')
    if (opts.length > 0) {
      categoryOptions.value = opts
    } else {
      message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
    }
  } catch (e) {
    console.warn('从 MDM 加载物料分类失败，使用硬编码兜底:', e)
    message.warning('部分下拉选项未能从主数据加载，已使用本地兜底')
  }
  // P1-007：支持顶部「新建」下拉通过 ?create=1 直接打开新增物料弹窗
  if (route.query.create === '1') {
    onAdd()
  }
})
</script>

<style scoped>
.raw-materials {
  width: 100%;
  max-width: 100%;
  overflow-x: hidden;
}

.page-header {
  margin-bottom: 12px;
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

.filter-card,
.table-card {
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  margin-bottom: 12px;
}

.stat-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.stat-item {
  flex: 1;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
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
}

.mat-id {
  font-family: monospace;
  font-weight: 600;
  color: var(--text-primary);
}

.num {
  font-family: monospace;
  font-size: 13px;
}

.cost {
  font-weight: 600;
  color: var(--text-primary);
}

.smiles-text {
  font-family: monospace;
  font-size: 12px;
  color: var(--text-muted);
}

.batch-expiry-cell {
  line-height: 1.4;
}

.batch-expiry-cell .expiry-sub {
  font-size: 11px;
  color: var(--text-muted);
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
}

.empty-state code {
  background: var(--light-bg);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

.toxic-tag {
  font-weight: 600;
}

:deep(.toxic-row) {
  background: rgba(220, 38, 38, 0.04) !important;
}

:deep(.toxic-row:hover > td) {
  background: rgba(220, 38, 38, 0.08) !important;
}

.form-hint-inline {
  margin-left: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

/* --- 版本历史 --- */
.version-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.version-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.version-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.version-number {
  font-weight: 600;
  font-family: monospace;
  color: var(--text-primary);
}

.active-tag {
  font-size: 11px;
}

.version-desc {
  font-size: 13px;
  color: var(--text-secondary);
}

.version-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.snapshot-card {
  margin-top: 12px;
  background: var(--light-bg);
}

.snapshot-json {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-primary);
  background: var(--light-bg);
  padding: 8px 12px;
  border-radius: 4px;
  max-height: 320px;
  overflow: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

/* --- 物料申请 + 来源标签 --- */
.request-actions {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--border);
}

.source-tag {
  cursor: default;
  font-weight: 500;
}

/* --- REACH 合规检查分区（AI Agent） --- */
.compliance-section {
  margin-top: 16px;
  padding: 12px 14px;
  background: var(--light-bg-card);
  border: 1px solid var(--border);
  border-left: 3px solid #8b5cf6;
  border-radius: var(--radius-lg);
}

.compliance-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.compliance-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.agent-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.ai-badge-mini {
  margin-left: 4px;
  font-size: 10px;
  line-height: 1.4;
  padding: 0 4px;
}

/* --- Task 13：合规证据展示 --- */
.evidence-link-row {
  margin-top: 2px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.evidence-link {
  font-size: 11px;
  padding: 0 4px;
}

.evidence-link-row .upload-btn {
  padding: 0;
  font-size: 11px;
  height: auto;
}

.evidence-detail-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.evidence-detail-list .evidence-link {
  font-size: 12px;
  padding: 2px 6px;
  border: 1px solid var(--border, #d9d9d9);
  border-radius: 4px;
}

.evidence-meta {
  font-size: 12px;
  color: var(--text-muted);
}

.evidence-empty {
  font-size: 12px;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
}

.empty-state {
  padding: 24px 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.empty-state code {
  background: var(--light-bg);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

.compact-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}

.compact-form :deep(.ant-form-item:last-child) {
  margin-bottom: 0;
}

:deep(.tabular-nums) {
  font-variant-numeric: tabular-nums;
  font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-size: 13px;
  color: var(--text-primary);
}

/* P2-4：关键 ID 列加粗 + 等宽字体 */
:deep(.id-col) {
  font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}

.smiles-text {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* --- 字典类型分组（表单中按字典类型展示属性字段） --- */
.dict-group {
  margin-bottom: 12px;
}

.dict-group-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
  padding: 4px 8px;
  background: var(--light-bg);
  border-radius: 4px;
  border-left: 3px solid var(--primary);
}

.text-muted {
  color: var(--text-muted);
}
</style>
