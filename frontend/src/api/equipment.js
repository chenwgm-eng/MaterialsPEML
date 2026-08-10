import client from './client'

export const listEquipment = (params) => client.get('/equipment', { params })

export const getEquipment = (id) => client.get(`/equipment/${encodeURIComponent(id)}`)

export const createEquipment = (data) => client.post('/equipment', data)

export const updateEquipment = (id, data) => client.put(`/equipment/${encodeURIComponent(id)}`, data)

export const deleteEquipment = (id) => client.delete(`/equipment/${encodeURIComponent(id)}`)