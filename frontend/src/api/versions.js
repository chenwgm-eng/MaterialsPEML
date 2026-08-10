import client from './client'

/** 创建版本快照 */
export const createVersion = (payload) => client.post('/versions', payload)

/** 获取实体的版本历史（按版本号倒序） */
export const listVersions = (entityType, entityId) =>
  client.get(`/versions/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`)

/** 设置为活跃版本（同实体其他版本自动失活） */
export const activateVersion = (versionId) =>
  client.put(`/versions/${encodeURIComponent(versionId)}/activate`)
