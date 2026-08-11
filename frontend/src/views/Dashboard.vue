<template>
  <div class="dashboard">
    <!-- Hero -->
    <section class="hero-section">
      <div class="page-container hero-content">
        <div class="hero-text">
          <h1 class="hero-title">AI 驱动的新材料研发闭环系统</h1>
          <p class="hero-desc">
            覆盖材料发现、合成路径设计、实验数据管理与 AI 闭环迭代的研发全流程平台。
            从输入目标到生成计划、执行计算、记录实验，统一在一个工作空间完成。
          </p>
          <div class="hero-actions">
            <a-dropdown placement="bottomLeft" trigger="click">
              <a-button id="hero-start-btn" type="primary" size="large" class="hero-btn-primary">
                <RocketOutlined /> 开始新材料研发 <DownOutlined />
              </a-button>
              <template #overlay>
                <a-menu @click="onStartMenuClick">
                  <a-menu-item key="research">从研发工作台开始</a-menu-item>
                  <a-menu-divider />
                  <a-menu-item key="PA6">从 PA6 开始</a-menu-item>
                  <a-menu-item key="PC">从 PC 开始</a-menu-item>
                  <a-menu-item key="ABS">从 ABS 开始</a-menu-item>
                  <a-menu-divider />
                  <a-menu-item key="custom">自定义</a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
            <a-button
              size="large"
              class="hero-btn-secondary"
              :class="{ 'continue-highlight': hasContinueRun }"
              :disabled="!hasContinueRun"
              @click="continueLast"
            >
              <PlayCircleOutlined /> 继续上次工作
            </a-button>
          </div>
        </div>
      </div>
    </section>

    <div class="page-container dashboard-body">
      <!-- 研究员首页 -->
      <template v-if="currentRole === 'researcher'">
        <div class="role-panel researcher-panel">
          <!-- 最近参与的项目 -->
          <section class="section-block">
            <SectionHeader title="最近参与的项目" subtitle="您近期参与的项目列表" />
            <SkeletonLoader
              v-if="researcherData.loading && researcherData.projects.length === 0"
              type="card"
              :rows="3"
              :delay="2000"
              cancellable
              loading-text="正在加载项目列表..."
              @cancel="researcherData.loading = false"
            />
            <template v-else>
              <a-row :gutter="[16, 16]">
                <a-col
                  v-for="proj in researcherData.projects"
                  :key="proj.project_id || proj.id"
                  :xs="24"
                  :sm="12"
                  :lg="8"
                >
                  <a-card hoverable class="role-item-card" @click="router.push(`/projects?project_id=${proj.project_id || proj.id}`)">
                    <div class="role-item-title">{{ proj.name || proj.project_name || '-' }}</div>
                    <div class="role-item-meta">
                      <a-tag :color="proj.status === 'completed' ? 'green' : 'blue'">{{ proj.status || '进行中' }}</a-tag>
                    </div>
                  </a-card>
                </a-col>
              </a-row>
              <EmptyAction
                v-if="!researcherData.loading && researcherData.projects.length === 0"
                title="暂无参与的项目"
                description="从快捷创建开始一个新的研发项目。"
                action-text="新建项目"
                :icon="markRaw(ProjectOutlined)"
                @action="router.push('/projects?create=1')"
              />
            </template>
          </section>

          <!-- 候选材料概览 -->
          <section class="section-block">
            <SectionHeader title="候选材料概览" subtitle="最近生成的候选材料" />
            <SkeletonLoader
              v-if="researcherData.loading && researcherData.candidates.length === 0"
              type="card"
              :rows="3"
              :delay="2000"
              cancellable
              loading-text="正在加载候选材料..."
              @cancel="researcherData.loading = false"
            />
            <template v-else>
              <a-row :gutter="[16, 16]">
                <a-col
                  v-for="cand in researcherData.candidates"
                  :key="cand.candidate_id || cand.id"
                  :xs="24"
                  :sm="12"
                  :lg="8"
                >
                  <a-card hoverable class="role-item-card" @click="router.push('/workbench')">
                    <div class="role-item-title">{{ cand.name || cand.formula || cand.candidate_id || '-' }}</div>
                    <div class="role-item-meta">
                      <a-tag v-if="cand.candidate_type">{{ cand.candidate_type }}</a-tag>
                      <a-tag v-if="cand.status">{{ cand.status }}</a-tag>
                    </div>
                  </a-card>
                </a-col>
              </a-row>
              <EmptyAction
                v-if="!researcherData.loading && researcherData.candidates.length === 0"
                title="暂无候选材料"
                description="前往候选设计生成新的候选材料。"
                action-text="生成候选材料"
                :icon="markRaw(ExperimentOutlined)"
                @action="router.push('/workbench')"
              />
            </template>
          </section>

          <!-- 待办任务 -->
          <section class="section-block">
            <SectionHeader title="待办任务" subtitle="需要您处理的审批与任务" />
            <SkeletonLoader
              v-if="researcherData.loading && researcherData.tasks.length === 0"
              type="list"
              :rows="4"
              :delay="2000"
              cancellable
              loading-text="正在加载待办任务..."
              @cancel="researcherData.loading = false"
            />
            <a-card v-else :bordered="false" class="role-list-card">
              <a-empty v-if="researcherData.tasks.length === 0" description="暂无待办任务" />
              <a-list v-else :data-source="researcherData.tasks" size="small">
                <template #renderItem="{ item }">
                  <a-list-item @click="router.push('/my-tasks')" class="role-list-item">
                    <a-list-item-meta>
                      <template #title>
                        <span>{{ item.title || item.name || item.request_id || '待办事项' }}</span>
                      </template>
                      <template #description>
                        {{ item.description || item.type || '' }}
                      </template>
                    </a-list-item-meta>
                    <template #actions>
                      <a-tag color="orange">待处理</a-tag>
                    </template>
                  </a-list-item>
                </template>
              </a-list>
            </a-card>
          </section>
        </div>
      </template>

      <!-- 项目经理首页 -->
      <template v-else-if="currentRole === 'pm'">
        <div class="role-panel pm-panel">
          <!-- 项目进度总览 -->
          <section class="section-block">
            <SectionHeader title="项目进度总览" subtitle="所管辖项目的进度情况" />
            <SkeletonLoader
              v-if="pmData.loading && pmData.projects.length === 0"
              type="card"
              :rows="3"
              :delay="2000"
              cancellable
              loading-text="正在加载项目进度..."
              @cancel="pmData.loading = false"
            />
            <template v-else>
              <a-row :gutter="[16, 16]">
                <a-col
                  v-for="proj in pmData.projects"
                  :key="proj.project_id || proj.id"
                  :xs="24"
                  :sm="12"
                  :lg="8"
                >
                  <a-card class="role-item-card" @click="router.push(`/projects?project_id=${proj.project_id || proj.id}`)">
                    <div class="role-item-title">{{ proj.name || proj.project_name || '-' }}</div>
                    <div class="role-item-progress">
                      <a-progress
                        :percent="projectProgress(proj)"
                        :stroke-color="projectProgress(proj) >= 100 ? '#52c41a' : 'var(--primary)'"
                        size="small"
                      />
                    </div>
                    <div class="role-item-meta">
                      <a-tag>{{ proj.status || '进行中' }}</a-tag>
                    </div>
                  </a-card>
                </a-col>
              </a-row>
              <EmptyAction
                v-if="!pmData.loading && pmData.projects.length === 0"
                title="暂无项目"
                description="创建一个新项目开始管理。"
                action-text="新建项目"
                :icon="markRaw(ProjectOutlined)"
                @action="router.push('/projects?create=1')"
              />
            </template>
          </section>

          <!-- 预算使用情况 -->
          <section class="section-block">
            <SectionHeader title="预算使用情况" subtitle="各预算项的消耗情况" />
            <SkeletonLoader
              v-if="pmData.loading && pmData.budgets.length === 0"
              type="list"
              :rows="4"
              :delay="2000"
              cancellable
              loading-text="正在加载预算数据..."
              @cancel="pmData.loading = false"
            />
            <a-card v-else :bordered="false" class="role-list-card">
              <a-empty v-if="pmData.budgets.length === 0" description="暂无预算数据" />
              <a-list v-else :data-source="pmData.budgets" size="small">
                <template #renderItem="{ item }">
                  <a-list-item>
                    <div class="budget-row">
                      <div class="budget-name">{{ item.scope || item.name || item.project_id || '预算项' }}</div>
                      <div class="budget-bar">
                        <a-progress
                          :percent="budgetUsage(item)"
                          :stroke-color="budgetUsage(item) > 100 ? '#ff4d4f' : budgetUsage(item) > 80 ? '#faad14' : 'var(--primary)'"
                          size="small"
                        />
                      </div>
                    </div>
                  </a-list-item>
                </template>
              </a-list>
            </a-card>
          </section>

          <!-- 风险预警 -->
          <section class="section-block">
            <SectionHeader title="风险预警" :subtitle="pmRisks.length === 0 ? '当前无风险' : `共 ${pmRisks.length} 项风险`" />
            <a-row :gutter="[16, 16]">
              <a-col
                v-for="risk in pmRisks"
                :key="risk.key"
                :xs="24"
                :sm="12"
                :lg="8"
              >
                <a-card :bordered="false" class="risk-card" :class="`risk-card--${risk.level}`">
                  <div class="risk-card-body">
                    <div class="risk-card-icon">
                      <WarningOutlined />
                    </div>
                    <div class="risk-card-text">
                      <div class="risk-card-title">{{ risk.title }}</div>
                      <div class="risk-card-desc">{{ risk.description }}</div>
                    </div>
                  </div>
                </a-card>
              </a-col>
              <a-col :span="24" v-if="pmRisks.length === 0">
                <EmptyAction
                  title="暂无风险预警"
                  description="所有项目按计划推进，预算正常。"
                  :icon="markRaw(WarningOutlined)"
                />
              </a-col>
            </a-row>
          </section>
        </div>
      </template>

      <!-- 审核员首页 -->
      <template v-else-if="currentRole === 'reviewer'">
        <div class="role-panel reviewer-panel">
          <!-- 待审核列表 -->
          <section class="section-block">
            <SectionHeader title="待审核列表" :subtitle="reviewerData.approvals.length === 0 ? '暂无待审核' : `共 ${reviewerData.approvals.length} 项待审核`" />
            <SkeletonLoader
              v-if="reviewerData.loading && reviewerData.approvals.length === 0"
              type="list"
              :rows="4"
              :delay="2000"
              cancellable
              loading-text="正在加载待审核列表..."
              @cancel="reviewerData.loading = false"
            />
            <a-card v-else :bordered="false" class="role-list-card">
              <a-empty v-if="reviewerData.approvals.length === 0" description="暂无待审核事项" />
              <a-list v-else :data-source="reviewerData.approvals" size="small">
                <template #renderItem="{ item }">
                  <a-list-item class="role-list-item" @click="router.push('/my-tasks?tab=approval')">
                    <a-list-item-meta>
                      <template #title>
                        <span>{{ item.title || item.name || item.order_id || '待审核事项' }}</span>
                      </template>
                      <template #description>
                        {{ item.description || item.type || '' }}
                      </template>
                    </a-list-item-meta>
                    <template #actions>
                      <a-tag color="orange">待审核</a-tag>
                    </template>
                  </a-list-item>
                </template>
              </a-list>
            </a-card>
          </section>

          <!-- QC 审核队列 -->
          <section class="section-block">
            <SectionHeader title="QC 审核队列" :subtitle="reviewerData.qcPending.length === 0 ? '队列为空' : `共 ${reviewerData.qcPending.length} 项待 QC 审核`" />
            <SkeletonLoader
              v-if="reviewerData.loading && reviewerData.qcPending.length === 0"
              type="list"
              :rows="4"
              :delay="2000"
              cancellable
              loading-text="正在加载 QC 审核队列..."
              @cancel="reviewerData.loading = false"
            />
            <a-card v-else :bordered="false" class="role-list-card">
              <a-empty v-if="reviewerData.qcPending.length === 0" description="暂无 QC 待审核" />
              <a-list v-else :data-source="reviewerData.qcPending" size="small">
                <template #renderItem="{ item }">
                  <a-list-item class="role-list-item" @click="router.push('/my-tasks?tab=qc_approval')">
                    <a-list-item-meta>
                      <template #title>
                        <span>{{ item.result_id || item.id || 'QC 待审项' }}</span>
                      </template>
                      <template #description>
                        {{ item.sample_id || item.experiment_id || '' }}
                      </template>
                    </a-list-item-meta>
                    <template #actions>
                      <a-tag color="blue">QC 待审</a-tag>
                    </template>
                  </a-list-item>
                </template>
              </a-list>
            </a-card>
          </section>

          <!-- 放行卡待审 -->
          <section class="section-block">
            <SectionHeader title="放行卡待审" :subtitle="reviewerData.releaseCards.length === 0 ? '暂无放行卡' : `共 ${reviewerData.releaseCards.length} 张待审`" />
            <SkeletonLoader
              v-if="reviewerData.loading && reviewerData.releaseCards.length === 0"
              type="list"
              :rows="4"
              :delay="2000"
              cancellable
              loading-text="正在加载放行卡..."
              @cancel="reviewerData.loading = false"
            />
            <a-card v-else :bordered="false" class="role-list-card">
              <a-empty v-if="reviewerData.releaseCards.length === 0" description="暂无放行卡待审" />
              <a-list v-else :data-source="reviewerData.releaseCards" size="small">
                <template #renderItem="{ item }">
                  <a-list-item class="role-list-item" @click="router.push('/my-tasks?tab=release')">
                    <a-list-item-meta>
                      <template #title>
                        <span>{{ item.card_id || item.id || '放行卡' }}</span>
                      </template>
                      <template #description>
                        {{ item.project_name || item.target || '' }}
                      </template>
                    </a-list-item-meta>
                    <template #actions>
                      <a-tag color="green">放行待审</a-tag>
                    </template>
                  </a-list-item>
                </template>
              </a-list>
            </a-card>
          </section>
        </div>
      </template>

      <!-- 实验员首页 -->
      <template v-else-if="currentRole === 'experimenter'">
        <div class="role-panel experimenter-panel">
          <!-- 待执行实验任务 -->
          <section class="section-block">
            <SectionHeader title="待执行实验任务" :subtitle="experimenterData.pendingOrders.length === 0 ? '暂无待执行任务' : `共 ${experimenterData.pendingOrders.length} 项待执行`" />
            <SkeletonLoader
              v-if="experimenterData.loading && experimenterData.pendingOrders.length === 0"
              type="list"
              :rows="4"
              :delay="2000"
              cancellable
              loading-text="正在加载实验任务..."
              @cancel="experimenterData.loading = false"
            />
            <a-card v-else :bordered="false" class="role-list-card">
              <a-empty v-if="experimenterData.pendingOrders.length === 0" description="暂无待执行实验任务" />
              <a-list v-else :data-source="experimenterData.pendingOrders" size="small">
                <template #renderItem="{ item }">
                  <a-list-item class="role-list-item" @click="router.push(`/experiment-workbench?order_id=${item.order_id || item.id}`)">
                    <a-list-item-meta>
                      <template #title>
                        <span>{{ item.order_id || item.id || '实验任务' }}</span>
                      </template>
                      <template #description>
                        {{ item.target || item.material || item.description || '' }}
                      </template>
                    </a-list-item-meta>
                    <template #actions>
                      <a-tag color="blue">待执行</a-tag>
                    </template>
                  </a-list-item>
                </template>
              </a-list>
            </a-card>
          </section>

          <!-- 最近样品 -->
          <section class="section-block">
            <SectionHeader title="样品管理" :subtitle="experimenterData.recentSamples.length === 0 ? '暂无样品' : `最近 ${experimenterData.recentSamples.length} 个样品`" />
            <SkeletonLoader
              v-if="experimenterData.loading && experimenterData.recentSamples.length === 0"
              type="card"
              :rows="3"
              :delay="2000"
              cancellable
              loading-text="正在加载样品数据..."
              @cancel="experimenterData.loading = false"
            />
            <template v-else>
              <a-row :gutter="[16, 16]">
                <a-col
                  v-for="sample in experimenterData.recentSamples"
                  :key="sample.sample_id || sample.id"
                  :xs="24"
                  :sm="12"
                  :lg="8"
                >
                  <a-card hoverable class="role-item-card" @click="router.push(`/samples?sample_id=${sample.sample_id || sample.id}`)">
                    <div class="role-item-title">{{ sample.name || sample.sample_id || '-' }}</div>
                    <div class="role-item-meta">
                      <a-tag :color="sampleStatusColor(sample.status)">{{ sampleStatusLabel(sample.status) }}</a-tag>
                      <a-tag v-if="sample.source_order_id">{{ sample.source_order_id }}</a-tag>
                    </div>
                  </a-card>
                </a-col>
              </a-row>
              <EmptyAction
                v-if="!experimenterData.loading && experimenterData.recentSamples.length === 0"
                title="暂无样品"
                description="创建一个新样品开始实验记录。"
                action-text="新建样品"
                :icon="markRaw(InboxOutlined)"
                @action="router.push('/samples?create=1')"
              />
            </template>
          </section>

          <!-- 设备预约 -->
          <section class="section-block">
            <SectionHeader title="设备预约" :subtitle="experimenterData.idleEquipment.length === 0 ? '暂无空闲设备' : `${experimenterData.idleEquipment.length} 台设备可预约`" />
            <SkeletonLoader
              v-if="experimenterData.loading && experimenterData.idleEquipment.length === 0"
              type="card"
              :rows="3"
              :delay="2000"
              cancellable
              loading-text="正在加载设备数据..."
              @cancel="experimenterData.loading = false"
            />
            <template v-else>
              <a-row :gutter="[16, 16]">
                <a-col
                  v-for="equip in experimenterData.idleEquipment"
                  :key="equip.equipment_id || equip.id"
                  :xs="24"
                  :sm="12"
                  :lg="8"
                >
                  <a-card hoverable class="role-item-card" @click="router.push('/equipment')">
                    <div class="role-item-title">{{ equip.name || equip.equipment_id || '-' }}</div>
                    <div class="role-item-meta">
                      <a-tag color="green">空闲</a-tag>
                      <a-tag v-if="equip.category">{{ equip.category }}</a-tag>
                      <a-tag v-if="equip.location">{{ equip.location }}</a-tag>
                    </div>
                  </a-card>
                </a-col>
              </a-row>
              <EmptyAction
                v-if="!experimenterData.loading && experimenterData.idleEquipment.length === 0"
                title="暂无空闲设备"
                description="所有设备均在占用中，请稍后再查看。"
                :icon="markRaw(ToolOutlined)"
                @action="router.push('/equipment')"
              />
            </template>
          </section>

          <!-- 数据录入入口 -->
          <section class="section-block">
            <SectionHeader title="数据录入" subtitle="快速录入实验数据" />
            <div class="quick-grid">
              <ActionCard
                :to="'/experiment-workbench'"
                :title="'实验工作台'"
                :description="'录入单条实验结果，触发 QC 自动检查'"
                :icon="markRaw(FormOutlined)"
              />
              <ActionCard
                :to="'/data-ingest'"
                :title="'批量导入'"
                :description="'Excel/CSV 历史数据批量导入，自动字段映射'"
                :icon="markRaw(ImportOutlined)"
              />
              <ActionCard
                :to="'/data-quality'"
                :title="'数据质量'"
                :description="'审核 QC 待检数据，确认有效或拒绝'"
                :icon="markRaw(SafetyCertificateOutlined)"
              />
            </div>
          </section>
        </div>
      </template>

      <!-- 管理员首页：保留现有 Dashboard 全部内容 -->
      <template v-else-if="currentRole === 'admin'">
        <div class="role-panel admin-panel">

      <!-- Stats：P0-1 可下钻卡片，口径与二级页面一致 -->
      <div class="stats-grid">
        <StatCard
          :value="stats.candidates"
          label="候选材料"
          :icon="markRaw(ExperimentOutlined)"
          icon-color="var(--primary)"
          :sub-text="`本周新增 ${stats.candidates_new_this_week}`"
          tooltip="累计候选材料数（与候选库同源），点击查看候选设计"
          clickable
          @click="router.push('/workbench')"
        />
        <StatCard
          :value="stats.experiments_active"
          label="实验任务"
          :icon="markRaw(DatabaseOutlined)"
          icon-color="var(--role-experiment)"
          :sub-text="`待审批 ${stats.experiments_pending_approval} · 总数 ${stats.experiments}`"
          tooltip="进行中实验任务（与实验工作台同源），点击查看实验数据"
          clickable
          @click="router.push('/experiments')"
        />
        <StatCard
          :value="stats.iterations"
          label="闭环迭代"
          :icon="markRaw(SyncOutlined)"
          icon-color="var(--role-dft)"
          :sub-text="`进行中 ${stats.iterations_active} · 近30天完成 ${stats.iterations_completed_30d}`"
          tooltip="正式 ECML 运行数（已隔离测试数据，与迭代历史「正式」视图同口径），点击查看迭代历史"
          clickable
          @click="router.push('/ecml/runs')"
        />
        <StatCard
          :value="stats.routes"
          label="合成路径"
          :icon="markRaw(BranchesOutlined)"
          icon-color="var(--role-synthesis)"
          :sub-text="synthesisSubText"
          :sub-alert="synthesisUnhealthy"
          tooltip="累计生成合成路径数（含失败尝试统计），点击查看合成路径规划"
          clickable
          @click="router.push('/synthesis')"
        />
      </div>

      <!-- 待办与预警：根据角色显示需要决策或行动的事项 -->
      <section class="section-block todo-alert-section">
        <SectionHeader title="待办与预警" :subtitle="todoSubtitle" />
        <div class="todo-alert-grid">
          <a-card
            v-for="item in todoItems"
            :key="item.key"
            class="todo-card"
            :class="`todo-card--${item.level}`"
            :bordered="false"
            size="small"
            hoverable
            @click="router.push(item.path)"
          >
            <div class="todo-card-body">
              <div class="todo-card-icon">
                <component :is="item.icon" />
              </div>
              <div class="todo-card-text">
                <div class="todo-card-title">{{ item.title }}</div>
                <div class="todo-card-desc">{{ item.description }}</div>
              </div>
              <div class="todo-card-count" v-if="item.count != null">{{ item.count }}</div>
            </div>
          </a-card>
          <EmptyAction
            v-if="todoItems.length === 0"
            title="暂无待办事项"
            description="所有事项已处理完毕，可以开始新的研发工作。"
            action-text="开始新材料研发"
            :icon="markRaw(RocketOutlined)"
            @action="router.push('/research')"
          />
        </div>
      </section>

      <!-- Continue Working -->
      <section id="continue-section" class="section-block">
        <SectionHeader title="继续工作" subtitle="从上次离开的地方接着推进" />
        <EmptyAction
          v-if="continueRuns.length === 0"
          title="暂无进行中的工作"
          description="从上方开始一次新材料研发，或从推荐模板快速启动。"
          action-text="开始新材料研发"
          :icon="markRaw(RocketOutlined)"
          @action="router.push('/research')"
        />
        <div v-else class="continue-grid">
          <div
            v-for="run in continueRuns"
            :key="run.run_id"
            class="continue-card"
          >
            <div class="continue-card-main">
              <div class="continue-target">{{ run.target || '-' }}</div>
              <div class="continue-progress">
                <a-progress
                  :percent="runProgress(run)"
                  :show-info="false"
                  size="small"
                  stroke-color="var(--primary)"
                />
              </div>
              <div class="continue-meta">
                <span class="continue-step">{{ getRunStepLabel(run) }}</span>
                <span>迭代 {{ run.iteration || 0 }}</span>
                <span>{{ formatRelativeTime(run.updated_at) }}</span>
              </div>
            </div>
            <div class="continue-actions">
              <a-button type="primary" size="small" @click="continueRun(run)">继续</a-button>
              <a-button size="small" class="continue-view-btn" @click="viewRun(run)">查看</a-button>
            </div>
          </div>
        </div>
      </section>

      <!-- Templates -->
      <section id="templates-section" class="section-block">
        <SectionHeader title="从模板开始" subtitle="选择常用材料快速进入研发流程" />
        <div class="template-grid">
          <ActionCard
            v-for="tmpl in templates"
            :key="tmpl.name"
            :to="tmplRoute(tmpl)"
            :title="tmpl.name"
            :description="tmplDesc(tmpl)"
            :icon="tmpl.icon"
          />
        </div>
      </section>

      <!-- Quick Actions -->
      <section class="section-block">
        <SectionHeader title="快速操作" subtitle="最常用的研发动作" />
        <div class="quick-grid">
          <ActionCard
            v-for="action in quickActions"
            :key="action.path"
            :to="action.path"
            :title="action.name"
            :description="action.desc"
            :icon="action.icon"
          />
        </div>
      </section>
        </div>
      </template>

      <!-- 只读访客首页 -->
      <template v-else>
        <div class="role-panel viewer-panel">
          <section class="section-block">
            <SectionHeader title="公开项目概览" subtitle="浏览平台上的公开项目" />
            <SkeletonLoader
              v-if="viewerData.loading && viewerData.projects.length === 0"
              type="card"
              :rows="3"
              :delay="2000"
              cancellable
              loading-text="正在加载公开项目..."
              @cancel="viewerData.loading = false"
            />
            <template v-else>
              <a-row :gutter="[16, 16]">
                <a-col
                  v-for="proj in viewerData.projects"
                  :key="proj.project_id || proj.id"
                  :xs="24"
                  :sm="12"
                  :lg="8"
                >
                  <a-card hoverable class="role-item-card" @click="router.push(`/projects?project_id=${proj.project_id || proj.id}`)">
                    <div class="role-item-title">{{ proj.name || proj.project_name || '-' }}</div>
                    <div class="role-item-meta">
                      <a-tag :color="proj.status === 'completed' ? 'green' : 'blue'">{{ proj.status || '进行中' }}</a-tag>
                    </div>
                  </a-card>
                </a-col>
              </a-row>
              <EmptyAction
                v-if="!viewerData.loading && viewerData.projects.length === 0"
                title="暂无公开项目"
                description="当前没有可浏览的公开项目。"
                action-text="登录查看更多"
                :icon="markRaw(ProjectOutlined)"
                @action="router.push('/research')"
              />
            </template>
          </section>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, markRaw, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ExperimentOutlined,
  DatabaseOutlined,
  SyncOutlined,
  BranchesOutlined,
  RocketOutlined,
  PlayCircleOutlined,
  AppstoreOutlined,
  ProfileOutlined,
  DownOutlined,
  ClockCircleOutlined,
  SearchOutlined,
  ProjectOutlined,
  FormOutlined,
  InboxOutlined,
  ImportOutlined,
  WarningOutlined,
  DollarOutlined,
  SafetyOutlined,
  SafetyCertificateOutlined,
  ToolOutlined,
} from '@ant-design/icons-vue'
import StatCard from '@/components/StatCard.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import ActionCard from '@/components/ActionCard.vue'
import EmptyAction from '@/components/EmptyAction.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
import { useSystemStore } from '@/stores/system'
import { useAuth } from '@/composables/useAuth'
import { getStats } from '@/api/system'
import { getEcmlRuns } from '@/api/ecml'
import client from '@/api/client'
import { listCandidates } from '@/api/candidates'
import { listPendingApprovals } from '@/api/approvals'
import { listQCPending, listExperimentOrders } from '@/api/experiments'
import { getReleaseCards } from '@/api/releaseCards'
import { getBudgets } from '@/api/controlPlane'
import { listSamples } from '@/api/samples'
import { listEquipment } from '@/api/equipment'

const router = useRouter()
const systemStore = useSystemStore()

const stats = ref({
  candidates: 0,
  candidates_new_this_week: 0,
  experiments: 0,
  experiments_active: 0,
  experiments_pending_approval: 0,
  iterations: 0,
  iterations_active: 0,
  iterations_completed_30d: 0,
  routes: 0,
  synthesis_success_rate: null,
})

// ASKCOS 服务健康度：可用率低于阈值即显示红色告警（P0-1 健康度指标）
const synthesisUnhealthy = computed(
  () => stats.value.synthesis_success_rate != null && stats.value.synthesis_success_rate < 0.5,
)
const synthesisSubText = computed(() => {
  const rate = stats.value.synthesis_success_rate
  if (rate == null) return '暂无规划记录'
  const pct = Math.round(rate * 100)
  return synthesisUnhealthy.value ? `服务异常 · 可用率 ${pct}%` : `服务可用率 ${pct}%`
})
const recentRuns = ref([])

// ===== 各角色面板独立数据 =====
// 研究员：最近项目、候选材料、待办任务
const researcherData = ref({
  projects: [],
  candidates: [],
  tasks: [],
  loading: false,
})

// 项目经理：项目进度、预算、风险
const pmData = ref({
  projects: [],
  budgets: [],
  loading: false,
})

// 审核员：待审核、QC 队列、放行卡
const reviewerData = ref({
  approvals: [],
  qcPending: [],
  releaseCards: [],
  loading: false,
})

// 只读访客：公开项目
const viewerData = ref({
  projects: [],
  loading: false,
})

// 实验员：待执行实验任务、样品管理、设备预约、数据录入
const experimenterData = ref({
  pendingOrders: [],
  recentSamples: [],
  idleEquipment: [],
  loading: false,
})

// 管理员判断（控制底部指标显示不同视角）+ 当前角色：统一走 useAuth composable
const { isAdmin, currentRole } = useAuth()

// 待办与预警：根据角色和现有 stats 数据生成
const todoItems = computed(() => {
  const items = []
  const role = currentRole.value
  // 待审批实验任务（所有角色可见）
  if (stats.value.experiments_pending_approval > 0) {
    items.push({
      key: 'pending-approval',
      title: '待审批实验任务',
      description: `${stats.value.experiments_pending_approval} 个实验任务等待审批`,
      count: stats.value.experiments_pending_approval,
      level: 'warning',
      icon: markRaw(ClockCircleOutlined),
      path: '/my-tasks?tab=approval',
    })
  }
  // 进行中闭环迭代（研究员/PM/管理员）
  if (stats.value.iterations_active > 0 && ['admin', 'pm', 'researcher'].includes(role)) {
    items.push({
      key: 'active-iterations',
      title: '进行中闭环迭代',
      description: `${stats.value.iterations_active} 个迭代正在进行，点击查看进度`,
      count: stats.value.iterations_active,
      level: 'info',
      icon: markRaw(SyncOutlined),
      path: '/ecml/runs',
    })
  }
  // 合成服务异常预警（管理员/研究员）
  if (synthesisUnhealthy.value && ['admin', 'researcher'].includes(role)) {
    items.push({
      key: 'synthesis-unhealthy',
      title: '合成服务可用率低',
      description: `ASKCOS 可用率 ${Math.round(stats.value.synthesis_success_rate * 100)}%，影响合成路径规划`,
      level: 'error',
      icon: markRaw(WarningOutlined),
      path: '/synthesis',
    })
  }
  // 管理员专属：平台运营指标
  if (role === 'admin') {
    if (stats.value.experiments === 0) {
      items.push({
        key: 'no-experiments',
        title: '实验数据为空',
        description: '系统尚未录入实验数据，建议创建首个实验任务',
        level: 'info',
        icon: markRaw(DatabaseOutlined),
        path: '/experiment-workbench',
      })
    }
  }
  return items
})

const todoSubtitle = computed(() => {
  const cnt = todoItems.value.length
  if (cnt === 0) return '当前无待办事项'
  return `共 ${cnt} 项待处理`
})

// 科研业务指标已移除（审查意见：总览页不再展示最近活动和集成服务指标）

const continueRuns = computed(() =>
  recentRuns.value.filter((r) => !r.is_complete).slice(0, 3),
)
const hasContinueRun = computed(() => continueRuns.value.length > 0)

const templates = [
  { name: 'PA6', materialType: 'polymer', target: 'PA6', icon: markRaw(ExperimentOutlined) },
  { name: 'PC', materialType: 'polymer', target: 'PC', icon: markRaw(ExperimentOutlined) },
  { name: 'ABS', materialType: 'polymer', target: 'ABS', icon: markRaw(ExperimentOutlined) },
  { name: 'PP', materialType: 'polymer', target: 'PP', icon: markRaw(ExperimentOutlined) },
  { name: 'PBT', materialType: 'polymer', target: 'PBT', icon: markRaw(ExperimentOutlined) },
  { name: '阻燃改性', materialType: 'polymer', target: 'flame_retardant_modification', icon: markRaw(ExperimentOutlined) },
]

const quickActions = [
  { path: '/research', name: '研发工作台', desc: '统一入口：目标 → 计划 → 执行', icon: markRaw(RocketOutlined) },
  { path: '/workbench', name: '候选设计', desc: '生成高分子/晶体候选材料', icon: markRaw(SearchOutlined) },
  { path: '/ecml', name: '实验闭环迭代', desc: '运行 7 步发现循环', icon: markRaw(SyncOutlined) },
  { path: '/experiments', name: '实验数据', desc: '查看湿实验数据', icon: markRaw(DatabaseOutlined) },
  { path: '/tools', name: 'AI 分析工具', desc: '浏览智能体工具', icon: markRaw(AppstoreOutlined) },
  { path: '/properties', name: '属性字典', desc: '管理材料性质选项', icon: markRaw(ProfileOutlined) },
]

function tmplRoute(tmpl) {
  if (tmpl.materialType === 'polymer') {
    return { path: '/workbench', query: { target: tmpl.target } }
  }
  return { path: '/workbench', query: { formula: tmpl.formula } }
}

function tmplDesc(tmpl) {
  return tmpl.materialType === 'polymer' ? '改性塑料发现' : '晶体材料发现'
}

function runProgress(run) {
  if (run.is_complete) return 100
  if (run.total_steps && run.completed_steps) {
    return Math.round((run.completed_steps.length / run.total_steps) * 100)
  }
  if (run.iteration) return Math.min(20 * run.iteration, 80)
  return 10
}

async function fetchStats() {
  try {
    const data = await getStats()
    stats.value = {
      candidates: data.candidates || 0,
      candidates_new_this_week: data.candidates_new_this_week || 0,
      experiments: data.experiments || 0,
      experiments_active: data.experiments_active || 0,
      experiments_pending_approval: data.experiments_pending_approval || 0,
      iterations: data.iterations || 0,
      iterations_active: data.iterations_active || 0,
      iterations_completed_30d: data.iterations_completed_30d || 0,
      routes: data.routes || 0,
      synthesis_success_rate: data.synthesis_success_rate ?? null,
    }
  } catch {
    // keep defaults of 0
  }
}

async function fetchRecentRuns() {
  // P0-1/P0-4：首页仅展示正式运行，测试数据已隔离（兼容旧后端无 run_source 字段）
  const isTest = (r) =>
    r.run_source ? r.run_source === 'test'
      : String(r.target || '').trim().toLowerCase().startsWith('test')
  const ecmlData = await getEcmlRuns(5).catch(() => ({ runs: [] }))
  const productionRuns = (ecmlData.runs || []).filter((r) => !isTest(r))
  recentRuns.value = productionRuns
}

// ===== 各角色面板独立数据加载 =====
// 统一从可能为数组或 {items:[...]} 的响应中提取数组
function toArray(resp) {
  if (Array.isArray(resp)) return resp
  if (resp && Array.isArray(resp.items)) return resp.items
  if (resp && Array.isArray(resp.data)) return resp.data
  return []
}

// 研究员：最近项目、候选材料、待办任务
async function fetchResearcherData() {
  researcherData.value.loading = true
  try {
    const [projectsRes, candidatesRes, tasksRes] = await Promise.all([
      client.get('/projects', { params: { limit: 6 } }).catch(() => []),
      listCandidates().catch(() => []),
      listPendingApprovals({ limit: 6 }).catch(() => []),
    ])
    researcherData.value.projects = toArray(projectsRes).slice(0, 6)
    researcherData.value.candidates = toArray(candidatesRes).slice(0, 6)
    researcherData.value.tasks = toArray(tasksRes).slice(0, 6)
  } catch {
    /* keep defaults */
  } finally {
    researcherData.value.loading = false
  }
}

// 项目经理：项目进度、预算、风险
async function fetchPmData() {
  pmData.value.loading = true
  try {
    const [projectsRes, budgetsRes] = await Promise.all([
      client.get('/projects', { params: { limit: 10 } }).catch(() => []),
      getBudgets().catch(() => []),
    ])
    pmData.value.projects = toArray(projectsRes).slice(0, 10)
    pmData.value.budgets = toArray(budgetsRes)
  } catch {
    /* keep defaults */
  } finally {
    pmData.value.loading = false
  }
}

// PM 风险预警：超期项目 + 预算超支
const pmRisks = computed(() => {
  const risks = []
  const now = Date.now()
  pmData.value.projects.forEach((p) => {
    const end = p.end_date || p.planned_end || p.deadline
    if (end && new Date(end).getTime() < now && p.status !== 'completed' && p.status !== 'done') {
      risks.push({
        key: `overdue-${p.project_id || p.id}`,
        title: '项目超期',
        description: `${p.name || p.project_name || '-'} 已超过计划结束日期`,
        level: 'error',
      })
    }
  })
  pmData.value.budgets.forEach((b) => {
    const used = b.used_amount ?? b.used ?? 0
    const total = b.total_amount ?? b.budget ?? b.allocated ?? 0
    if (total > 0 && used > total) {
      risks.push({
        key: `overrun-${b.scope || b.project_id || b.id}`,
        title: '预算超支',
        description: `${b.scope || b.name || '预算项'} 已使用 ${Math.round((used / total) * 100)}%`,
        level: 'error',
      })
    } else if (total > 0 && used / total > 0.8) {
      risks.push({
        key: `near-overrun-${b.scope || b.project_id || b.id}`,
        title: '预算接近超支',
        description: `${b.scope || b.name || '预算项'} 已使用 ${Math.round((used / total) * 100)}%`,
        level: 'warning',
      })
    }
  })
  return risks
})

// 审核员：待审核、QC 队列、放行卡
async function fetchReviewerData() {
  reviewerData.value.loading = true
  try {
    const [approvalsRes, qcRes, releaseRes] = await Promise.all([
      listPendingApprovals({ limit: 8 }).catch(() => []),
      listQCPending().catch(() => []),
      getReleaseCards({ status: 'pending' }).catch(() => []),
    ])
    reviewerData.value.approvals = toArray(approvalsRes).slice(0, 8)
    reviewerData.value.qcPending = toArray(qcRes).slice(0, 8)
    reviewerData.value.releaseCards = toArray(releaseRes).slice(0, 8)
  } catch {
    /* keep defaults */
  } finally {
    reviewerData.value.loading = false
  }
}

// 只读访客：公开项目概览
async function fetchViewerData() {
  viewerData.value.loading = true
  try {
    const res = await client.get('/projects', { params: { limit: 8 } }).catch(() => [])
    viewerData.value.projects = toArray(res).slice(0, 8)
  } catch {
    /* keep defaults */
  } finally {
    viewerData.value.loading = false
  }
}

// 实验员：待执行实验任务、最近样品、空闲设备
async function fetchExperimenterData() {
  experimenterData.value.loading = true
  try {
    const [ordersRes, samplesRes, equipRes] = await Promise.all([
      listExperimentOrders({ status: 'approved' }).catch(() => []),
      listSamples().catch(() => []),
      listEquipment({ status: 'idle' }).catch(() => []),
    ])
    experimenterData.value.pendingOrders = toArray(ordersRes).slice(0, 8)
    experimenterData.value.recentSamples = toArray(samplesRes).slice(0, 8)
    experimenterData.value.idleEquipment = toArray(equipRes).slice(0, 6)
  } catch {
    /* keep defaults */
  } finally {
    experimenterData.value.loading = false
  }
}

// 按角色加载对应面板数据
async function loadRolePanelData() {
  const role = currentRole.value
  if (role === 'researcher') {
    await fetchResearcherData()
  } else if (role === 'pm') {
    await fetchPmData()
  } else if (role === 'reviewer') {
    await fetchReviewerData()
  } else if (role === 'experimenter') {
    await fetchExperimenterData()
  } else if (role === 'viewer') {
    await fetchViewerData()
  }
  // admin 沿用现有 fetchStats + fetchRecentRuns，无需额外加载
}

// 样品状态颜色与标签（实验员面板）
function sampleStatusColor(status) {
  const map = {
    created: '#64748b',
    in_storage: '#3b82f6',
    in_use: '#1d4ed8',
    consumed: '#f59e0b',
    discarded: '#ef4444',
  }
  return map[status] || '#64748b'
}
function sampleStatusLabel(status) {
  const map = {
    created: '已创建',
    in_storage: '在库',
    in_use: '使用中',
    consumed: '已消耗',
    discarded: '已废弃',
  }
  return map[status] || status || '未知'
}

// 项目进度计算
function projectProgress(p) {
  if (p.progress != null) return Math.min(100, Math.max(0, Math.round(p.progress)))
  if (p.completion_rate != null) return Math.min(100, Math.max(0, Math.round(p.completion_rate * 100)))
  if (p.status === 'completed' || p.status === 'done') return 100
  return 0
}

// 预算使用率
function budgetUsage(b) {
  const used = b.used_amount ?? b.used ?? 0
  const total = b.total_amount ?? b.budget ?? b.allocated ?? 0
  if (total <= 0) return 0
  return Math.round((used / total) * 100)
}

function formatRelativeTime(dateStr) {
  if (!dateStr) return ''
  const then = new Date(dateStr).getTime()
  if (Number.isNaN(then)) return ''
  const diff = Math.max(0, Date.now() - then)
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return '刚刚'
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  const day = Math.floor(hr / 24)
  if (day < 30) return `${day} 天前`
  return new Date(dateStr).toLocaleDateString()
}

function getRunStepLabel(run) {
  if (run.is_complete) return '已完成'
  if (run.current_step) return run.current_step
  if (run.iteration) return `迭代 ${run.iteration}`
  return '准备中'
}

function continueRun(run) {
  router.push({ path: '/ecml', query: { run_id: run.run_id } })
}

function viewRun(run) {
  router.push({ path: '/ecml', query: { run_id: run.run_id } })
}

function continueLast() {
  const run = continueRuns.value[0]
  if (run) continueRun(run)
}

function onStartMenuClick({ key }) {
  if (key === 'research') {
    router.push('/research')
    return
  }
  if (key === 'custom') {
    router.push('/workbench')
    return
  }
  if (key === 'PA6' || key === 'PC' || key === 'ABS') {
    router.push({ path: '/workbench', query: { target: key } })
    return
  }
  router.push({ path: '/workbench', query: { formula: key } })
}

// P1-008: 定时刷新统计卡片（30 秒间隔，仅管理员看板需要）
let _refreshTimer = null
const lastRefreshTime = ref(null)

function startAutoRefresh() {
  // 仅管理员面板使用 stats + recentRuns，其他角色无需定时刷新
  if (currentRole.value !== 'admin') return
  _refreshTimer = setInterval(async () => {
    try {
      await Promise.all([fetchStats(), fetchRecentRuns()])
      lastRefreshTime.value = new Date().toLocaleTimeString('zh-CN')
    } catch {
      /* ignore refresh errors */
    }
  }, 30000)
}

onMounted(async () => {
  try {
    await systemStore.fetchHealth()
  } catch {
    /* ignore */
  }
  const role = currentRole.value
  if (role === 'admin') {
    // 管理员：加载现有看板数据（stats + recentRuns）
    await Promise.all([fetchStats(), fetchRecentRuns()])
    lastRefreshTime.value = new Date().toLocaleTimeString('zh-CN')
  } else {
    // 其他角色：加载对应面板数据（独立加载，避免不必要请求）
    await loadRolePanelData()
  }
  startAutoRefresh()
})

onUnmounted(() => {
  if (_refreshTimer) {
    clearInterval(_refreshTimer)
    _refreshTimer = null
  }
})
</script>

<style scoped>
.dashboard {
  min-height: 100%;
  background: var(--light-bg);
  color: var(--text-primary);
  color-scheme: light;
}

/* ===== Hero ===== */
.hero-section {
  position: relative;
  padding: 48px 0 56px;
  background: var(--realsee-surface);
  border-bottom: 1px solid var(--border);
  overflow: hidden;
}

.hero-content {
  position: relative;
  z-index: 1;
}

.hero-text {
  max-width: 680px;
}

.hero-title {
  font-size: var(--font-size-5xl);
  font-weight: var(--font-weight-black);
  color: var(--text-primary);
  margin: 0 0 16px;
  line-height: 1.1;
  letter-spacing: -0.02em;
  text-wrap: balance;
}

.hero-desc {
  font-size: var(--font-size-lg);
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0 0 28px;
}

.hero-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.hero-btn-primary {
  border-radius: var(--radius-lg);
  height: 48px;
  padding: 0 22px;
  font-weight: var(--font-weight-semibold);
}

.hero-btn-secondary {
  border-radius: var(--radius-lg);
  height: 48px;
  padding: 0 22px;
  color: var(--text-primary);
  border-color: var(--border);
  background: transparent;
}

.hero-btn-secondary:hover:not(:disabled) {
  border-color: var(--primary);
  background: var(--primary-bg);
  color: var(--text-primary);
}

.hero-btn-secondary.continue-highlight {
  border-color: var(--primary);
  background: var(--primary-bg);
  box-shadow: 0 0 0 1px var(--primary);
}

.hero-btn-secondary:disabled {
  color: var(--text-muted);
  border-color: var(--border);
  background: transparent;
  opacity: 0.6;
}

/* ===== Body ===== */
.dashboard-body {
  padding: 0 var(--page-gutter) var(--space-xl);
}

/* ===== Stats ===== */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-md);
  margin: -44px 0 var(--space-xl);
  position: relative;
  z-index: 2;
}

.stats-grid :deep(.stat-card) {
  background: var(--realsee-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-card);
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}

.stats-grid :deep(.stat-card:hover) {
  transform: translateY(-2px);
  box-shadow: var(--shadow-hover);
}

.stats-grid :deep(.stat-icon) {
  background: var(--primary-bg);
  border: 1px solid var(--primary-border);
}

.stats-grid :deep(.stat-value) {
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.stats-grid :deep(.stat-label) {
  color: var(--text-secondary);
}

/* ===== Sections ===== */
.section-block {
  margin-bottom: var(--space-xl);
}

/* ===== 待办与预警 ===== */
.todo-alert-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-md);
}

.todo-card {
  cursor: pointer;
  border-radius: var(--radius-lg) !important;
  transition: box-shadow var(--transition), transform var(--transition);
}

.todo-card:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-hover);
}

.todo-card-body {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.todo-card-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.todo-card--warning .todo-card-icon {
  background: var(--warning-bg);
  color: var(--warning);
}

.todo-card--info .todo-card-icon {
  background: var(--info-bg);
  color: var(--info);
}

.todo-card--error .todo-card-icon {
  background: var(--error-bg);
  color: var(--error);
}

.todo-card-text {
  flex: 1;
  min-width: 0;
}

.todo-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.todo-card-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.todo-card-count {
  flex-shrink: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

/* ===== Continue Working ===== */
.continue-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-md);
}

.continue-card {
  background: var(--realsee-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  padding: var(--space-lg);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  transition: border-color var(--transition-fast), background var(--transition-fast), transform var(--transition-fast);
}

.continue-card:hover {
  border-color: var(--primary);
  background: var(--light-bg-hover);
  transform: translateY(-2px);
}

.continue-card-main {
  flex: 1;
  min-width: 0;
}

.continue-target {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.continue-progress {
  margin-bottom: 8px;
}

.continue-progress :deep(.ant-progress-inner) {
  background-color: var(--border-light);
}

.continue-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.continue-step {
  color: var(--primary);
  font-weight: var(--font-weight-semibold);
}

.continue-actions {
  display: flex;
  gap: var(--space-sm);
  flex-shrink: 0;
}

.continue-view-btn {
  color: var(--text-primary);
  border-color: var(--border);
  background: transparent;
}

.continue-view-btn:hover {
  border-color: var(--primary);
  color: var(--text-primary);
}

/* ===== Templates / Quick Actions ===== */
.template-grid,
.quick-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-md);
}

/* ===== Responsive ===== */
@media (max-width: 1200px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .template-grid,
  .quick-grid { grid-template-columns: repeat(2, 1fr); }
  .continue-grid { grid-template-columns: 1fr; }
  .hero-title { font-size: var(--font-size-4xl); }
}

@media (max-width: 699px) {
  .stats-grid { grid-template-columns: 1fr; }
  .template-grid,
  .quick-grid { grid-template-columns: 1fr; }
  .continue-card { flex-direction: column; align-items: flex-start; }
  .hero-title { font-size: var(--font-size-3xl); }
  .hero-section { padding: 28px 0 32px; }
  .hero-actions { flex-direction: column; width: 100%; }
  .hero-btn-primary,
  .hero-btn-secondary { width: 100%; }
  .metrics-grid { grid-template-columns: repeat(2, 1fr); }
  .budget-name { width: 100px; }
  .budget-row { flex-direction: column; align-items: flex-start; gap: 4px; }
}

/* ===== Reduced motion ===== */
@media (prefers-reduced-motion: reduce) {
  .hero-btn-primary,
  .hero-btn-secondary,
  .stats-grid :deep(.stat-card),
  .continue-card,
  .action-card {
    transition: none;
  }
  .stats-grid :deep(.stat-card:hover),
  .continue-card:hover {
    transform: none;
  }
}

/* ===== 角色面板通用样式 ===== */
.role-panel {
  padding-top: var(--space-md);
}

/* 角色面板内的卡片项 */
.role-item-card {
  height: 100%;
  border-radius: var(--radius-lg) !important;
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
  cursor: pointer;
}

.role-item-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-hover);
}

.role-item-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.role-item-progress {
  margin-bottom: 8px;
}

.role-item-progress :deep(.ant-progress-inner) {
  background-color: var(--border-light);
}

/* 角色面板内的列表卡片 */
.role-list-card {
  border-radius: var(--radius-lg) !important;
  background: var(--realsee-surface);
  border: 1px solid var(--border);
}

.role-list-item {
  cursor: pointer;
  transition: background var(--transition-fast);
}

.role-list-item:hover {
  background: var(--light-bg-hover);
}

/* 预算行 */
.budget-row {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  width: 100%;
}

.budget-name {
  flex-shrink: 0;
  width: 160px;
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.budget-bar {
  flex: 1;
  min-width: 0;
}

/* 风险卡片 */
.risk-card {
  border-radius: var(--radius-lg) !important;
}

.risk-card--error {
  border-left: 3px solid var(--error) !important;
}

.risk-card--warning {
  border-left: 3px solid var(--warning) !important;
}

.risk-card-body {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.risk-card-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.risk-card--error .risk-card-icon {
  background: var(--error-bg);
  color: var(--error);
}

.risk-card--warning .risk-card-icon {
  background: var(--warning-bg);
  color: var(--warning);
}

.risk-card-text {
  flex: 1;
  min-width: 0;
}

.risk-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.risk-card-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}
</style>
