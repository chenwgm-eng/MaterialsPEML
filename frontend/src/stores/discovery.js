import { defineStore } from 'pinia'
import { readonly, ref } from 'vue'
import { discoverCrystal, discoverPolymer, routeMaterial, generateCandidates, agentGenerateCandidates, agentGenerateAsync, getAgentGenerateStatus, batchPredictCandidates } from '@/api/discovery'

export const useDiscoveryStore = defineStore('discovery', () => {
  const crystalCandidates = ref([])
  const polymerCandidates = ref([])
  const generatedCandidates = ref([])
  const routeResult = ref(null)
  const loading = ref(false)
  const currentOperation = ref('')
  // Agent 创造性生成相关状态
  const agentReasoning = ref('')
  const agentInfo = ref(null)
  const generateMode = ref('pure_llm')
  // 异步生成进度
  const agentProgress = ref(0)        // 0-100
  const agentStepLabel = ref('')      // 当前步骤描述
  const agentTaskId = ref('')         // 异步任务 ID
  // 需求7：批量预测状态（三点状态指示）
  const batchPredicting = ref(false)  // 是否正在批量预测
  const candidateStatusMap = ref({})  // { candidateKey: { prediction, synthesis, verification } }

  async function findCrystal(params) {
    loading.value = true
    currentOperation.value = 'crystal'
    try {
      const res = await discoverCrystal(params)
      crystalCandidates.value = res.candidates || []
      return res
    } finally {
      loading.value = false
      currentOperation.value = ''
    }
  }

  async function agentGenerate(params) {
    loading.value = true
    currentOperation.value = 'agent-generate'
    agentProgress.value = 0
    agentStepLabel.value = '正在启动 Agent…'
    try {
      // 优先使用异步接口（带进度反馈），失败时回退到同步接口
      const startRes = await agentGenerateAsync(params)
      const taskId = startRes?.task_id
      let res
      if (!taskId) {
        // 回退到同步路径：添加 120 秒超时保护，避免 LLM 调用挂起导致前端永久 loading
        agentStepLabel.value = 'Agent 正在生成（同步模式）…'
        const SYNC_TIMEOUT = 120000
        let timeoutId = null
        const timeoutPromise = new Promise((_, reject) => {
          timeoutId = setTimeout(() => reject(new Error('Agent 生成超时（120 秒），请稍后重试或检查 LLM 服务状态')), SYNC_TIMEOUT)
        })
        try {
          res = await Promise.race([
            agentGenerateCandidates(params),
            timeoutPromise,
          ])
        } finally {
          // 无论成功还是超时，都清除计时器，避免资源泄漏
          if (timeoutId) clearTimeout(timeoutId)
        }
        crystalCandidates.value = res.candidates || []
        agentReasoning.value = res.reasoning || ''
        agentInfo.value = res.agent || null
        agentProgress.value = 100
      } else {
        agentTaskId.value = taskId
        // 轮询进度（2 秒间隔，最长 120 秒）
        res = await _pollAgentProgress(taskId)
        crystalCandidates.value = res.candidates || []
        agentReasoning.value = res.reasoning || ''
        agentInfo.value = res.agent || null
        agentProgress.value = 100
        agentStepLabel.value = '生成完成'
      }
      // 需求7：生成完成后自动触发批量预测（非阻塞，失败不影响主流程）
      _autoBatchPredict(res.candidates || [], params)
      return res
    } finally {
      loading.value = false
      currentOperation.value = ''
    }
  }

  // 需求7：自动批量预测——生成候选后自动执行，更新三点状态
  async function _autoBatchPredict(candidates, params) {
    if (!candidates?.length) return
    batchPredicting.value = true
    agentStepLabel.value = '正在批量预测候选属性…'
    try {
      const res = await batchPredictCandidates({
        candidates,
        material_kind: params?.material_kind || 'crystal',
        target_properties: params?.target_properties || [],
        model_type: params?.model_type || null,
        run_synthesis_check: true,
      })
      const results = res?.results || []
      const newStatusMap = {}
      const updatedCandidates = [...crystalCandidates.value]
      results.forEach((r) => {
        const key = r.candidate_key
        newStatusMap[key] = {
          prediction: r.prediction_status,
          synthesis: r.synthesis_status,
          manufacturability: r.manufacturability_status,
          synthesisScore: r.synthesis_score,
          manufacturabilityScore: r.manufacturability_score,
          targetsMet: r.targets_met,
          totalTargets: r.total_targets,
        }
        // 回填预测值到候选对象（用后端返回的回填后 candidate）
        if (r.candidate) {
          const idx = updatedCandidates.findIndex((c) =>
            _matchCandidateKey(c, key)
          )
          if (idx >= 0) {
            updatedCandidates[idx] = { ...updatedCandidates[idx], ...r.candidate }
          }
        }
      })
      candidateStatusMap.value = newStatusMap
      crystalCandidates.value = updatedCandidates
      agentStepLabel.value = '批量预测完成'
    } catch (e) {
      // 批量预测失败不阻塞主流程，三点状态保持 pending
      agentStepLabel.value = '批量预测失败（不影响候选查看）'
    } finally {
      batchPredicting.value = false
    }
  }

  function _matchCandidateKey(candidate, key) {
    return (
      (candidate.candidate_id && candidate.candidate_id === key) ||
      (candidate.id && candidate.id === key) ||
      (candidate.material_id && candidate.material_id === key) ||
      (candidate.formula && candidate.formula === key) ||
      (candidate.smiles && candidate.smiles === key)
    )
  }

  // 需求7：手动触发批量预测（供前端按钮调用）
  async function batchPredict(params) {
    batchPredicting.value = true
    try {
      const candidates = params?.candidates || crystalCandidates.value
      await _autoBatchPredict(candidates, params)
    } finally {
      batchPredicting.value = false
    }
  }

  async function _pollAgentProgress(taskId) {
    const POLL_INTERVAL = 2000
    const MAX_DURATION = 300000
    const startTime = Date.now()
    while (true) {
      const elapsed = Date.now() - startTime
      if (elapsed > MAX_DURATION) {
        throw new Error('Agent 生成超时，后台可能仍在处理')
      }
      const status = await getAgentGenerateStatus(taskId)
      agentProgress.value = status?.progress || 0
      agentStepLabel.value = status?.step_label || ''
      if (status?.status === 'completed' && status?.result) {
        return status.result
      }
      if (status?.status === 'failed') {
        throw new Error(status?.error || 'Agent 生成失败')
      }
      // 等待下一次轮询
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL))
    }
  }

  async function findPolymer(params) {
    loading.value = true
    currentOperation.value = 'polymer'
    try {
      const res = await discoverPolymer(params)
      polymerCandidates.value = res.candidates || []
      return res
    } finally {
      loading.value = false
      currentOperation.value = ''
    }
  }

  async function generate(params) {
    loading.value = true
    currentOperation.value = 'generate'
    try {
      const res = await generateCandidates(params)
      generatedCandidates.value = res.candidates || []
      return res
    } finally {
      loading.value = false
      currentOperation.value = ''
    }
  }

  async function route(input) {
    loading.value = true
    currentOperation.value = 'route'
    try {
      routeResult.value = await routeMaterial(input)
      return routeResult.value
    } finally {
      loading.value = false
      currentOperation.value = ''
    }
  }

  function clearCandidates() {
    crystalCandidates.value = []
    polymerCandidates.value = []
    generatedCandidates.value = []
    routeResult.value = null
    agentReasoning.value = ''
    agentInfo.value = null
    agentProgress.value = 0
    agentStepLabel.value = ''
    agentTaskId.value = ''
    batchPredicting.value = false
    candidateStatusMap.value = {}
  }

  return {
    crystalCandidates: readonly(crystalCandidates),
    polymerCandidates: readonly(polymerCandidates),
    generatedCandidates: readonly(generatedCandidates),
    routeResult: readonly(routeResult),
    loading: readonly(loading),
    currentOperation: readonly(currentOperation),
    agentReasoning: readonly(agentReasoning),
    agentInfo: readonly(agentInfo),
    generateMode,
    agentProgress: readonly(agentProgress),
    agentStepLabel: readonly(agentStepLabel),
    agentTaskId: readonly(agentTaskId),
    batchPredicting: readonly(batchPredicting),
    candidateStatusMap: readonly(candidateStatusMap),
    findCrystal,
    findPolymer,
    generate,
    route,
    agentGenerate,
    batchPredict,
    clearCandidates,
  }
})
