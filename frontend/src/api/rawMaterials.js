import client from './client'

export const getRawMaterials = (category = '') =>
  client.get('/raw-materials', { params: category ? { category } : {} })

export const getRawMaterial = (id) =>
  client.get(`/raw-materials/${encodeURIComponent(id)}`)

/** 新增物料规格 */
export const createRawMaterial = (payload) =>
  client.post('/raw-materials', payload)

/** 编辑物料规格 */
export const updateRawMaterial = (id, payload) =>
  client.put(`/raw-materials/${encodeURIComponent(id)}`, payload)

/** 删除物料（被配方引用的物料会被后端拒绝） */
export const deleteRawMaterial = (id) =>
  client.delete(`/raw-materials/${encodeURIComponent(id)}`)

/** 检查候选材料所需原料在企业物料库中的可得性 */
export const checkMaterialsAvailability = (candidates, quantityKg = 1.0) =>
  client.post('/raw-materials/check-availability', {
    candidates,
    quantity_kg: quantityKg,
  })
