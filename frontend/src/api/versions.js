import client from './client'

/** 创建版本快照 */
export const createVersion = (payload) => client.post('/versions', payload)

/** 获取实体的版本历史（按版本号倒序） */
export const listVersions = (entityType, entityId) =>
  client.get(`/versions/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`)

/** 获取最新版本（优先活跃版本，否则最大版本号） */
export const getLatestVersion = (entityType, entityId) =>
  client.get(`/versions/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}/latest`)

/** 设置为活跃版本（同实体其他版本自动失活） */
export const activateVersion = (versionId) =>
  client.put(`/versions/${encodeURIComponent(versionId)}/activate`)

/** 列出所有实体的活跃版本（可选 entity_type 过滤） */
export const listActiveVersions = (entityType = '') =>
  client.get('/versions', { params: entityType ? { entity_type: entityType } : {} })
