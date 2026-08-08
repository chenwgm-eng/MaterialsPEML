import client from './client'

/** 按关键词搜索材料领域文献 */
export const searchLiterature = (query, limit = 10) =>
  client.post('/knowledge/search', { query, limit })

/** 从文献列表抽取实体（材料/性能/方法/应用/机构） */
export const extractEntities = (papers) =>
  client.post('/knowledge/entities', { papers })

/** 从文献列表构建知识图谱（节点 + 边） */
export const buildKnowledgeGraph = (papers) =>
  client.post('/knowledge/graph', { papers })

/** 保存知识图谱快照 */
export const saveKnowledgeGraph = (payload) =>
  client.post('/knowledge/graphs', payload)

/** 增量更新已有知识图谱（合并节点/边） */
export const updateKnowledgeGraph = (graphId, payload) =>
  client.put(`/knowledge/graphs/${encodeURIComponent(graphId)}`, payload)

/** 列出已保存的知识图谱 */
export const listKnowledgeGraphs = (limit = 50) =>
  client.get('/knowledge/graphs', { params: { limit } })

/** 获取单个知识图谱详情（含完整节点与边） */
export const getKnowledgeGraph = (graphId) =>
  client.get(`/knowledge/graphs/${encodeURIComponent(graphId)}`)

/** 删除指定知识图谱 */
export const deleteKnowledgeGraph = (graphId) =>
  client.delete(`/knowledge/graphs/${encodeURIComponent(graphId)}`)

// ─────────────────────────────────────────────────────────────────────────
// 材料知识资产库（papers / materials / claims）
// ─────────────────────────────────────────────────────────────────────────

/** 检索文献资产 */
export const listPapers = ({ query = '', source = '', sourceTier = '', limit = 50, offset = 0 } = {}) =>
  client.get('/knowledge/papers', {
    params: { query, source, source_tier: sourceTier, limit, offset },
  })

/** 获取单篇文献详情 */
export const getPaper = (paperId) =>
  client.get(`/knowledge/papers/${encodeURIComponent(paperId)}`)

/** 手动录入文献 */
export const createPaper = (payload) =>
  client.post('/knowledge/papers', payload)

/** 删除文献 */
export const deletePaper = (paperId) =>
  client.delete(`/knowledge/papers/${encodeURIComponent(paperId)}`)

/** 列出材料卡片 */
export const listMaterials = ({ query = '', category = '', limit = 50, offset = 0 } = {}) =>
  client.get('/knowledge/materials', {
    params: { query, category, limit, offset },
  })

/** 获取材料卡片详情（含关联文献与主张） */
export const getMaterial = (materialId) =>
  client.get(`/knowledge/materials/${encodeURIComponent(materialId)}`)

/** 创建/更新材料卡片 */
export const upsertMaterial = (payload) =>
  client.post('/knowledge/materials', payload)

/** 删除材料卡片 */
export const deleteMaterial = (materialId) =>
  client.delete(`/knowledge/materials/${encodeURIComponent(materialId)}`)

/** 列出材料的主张 */
export const listClaims = ({ materialId, claimType = '', limit = 100 }) =>
  client.get('/knowledge/claims', {
    params: { material_id: materialId, claim_type: claimType, limit },
  })

/** 添加一条主张 */
export const createClaim = (payload) =>
  client.post('/knowledge/claims', payload)

/** 删除主张 */
export const deleteClaim = (claimId) =>
  client.delete(`/knowledge/claims/${encodeURIComponent(claimId)}`)

/** 将检索结果批量入库为知识资产 */
export const ingestPapers = ({ papers, defaultSource = 'search', query = '' }) =>
  client.post('/knowledge/ingest', { papers, default_source: defaultSource, query })

/** 一体化：检索 + 入库 */
export const searchAndIngest = (query, limit = 10) =>
  client.post('/knowledge/search_and_ingest', { query, limit })

/** LLM 驱动的主张抽取：从材料关联文献中自动提取结构化主张 */
export const extractClaims = (materialId, paperLimit = 10) =>
  client.post('/knowledge/extract_claims', { material_id: materialId, paper_limit: paperLimit })
