import client from './client'

export const getCategories = () => client.get('/properties/categories')
export const getFields = (params) => client.get('/properties/fields', { params })
export const getStats = () => client.get('/properties/stats')
export const getOptions = (params, config = {}) => client.get('/properties/options', { ...config, params })
export const addCustomField = (data) => client.post('/properties/custom', data)
export const removeCustomField = (key) => client.delete(`/properties/custom/${encodeURIComponent(key)}`)

// 属性字段模板（按实验类型）
export function getPropertyTemplate(experimentType) {
  return client.get(`/properties/templates/${experimentType}`)
}

export function listPropertyTemplates() {
  return client.get('/properties/templates')
}

// 物料类型属性模板（属性字典闭环）
export function getMaterialTypeTemplates() {
  return client.get('/properties/material-type-templates')
}

export function getMaterialTypeTemplate(materialType) {
  return client.get(`/properties/material-type-templates/${encodeURIComponent(materialType)}`)
}

export function updateMaterialTypeTemplate(materialType, fieldKeys) {
  return client.put(`/properties/material-type-templates/${encodeURIComponent(materialType)}`, {
    field_keys: fieldKeys,
  })
}

// 跨尺度建模
export function crossScalePredict(data) {
  return client.post('/properties/cross_scale', data)
}
