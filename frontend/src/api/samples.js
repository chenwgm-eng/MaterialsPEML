import client from './client'

export const listSamples = (params = {}) => client.get('/samples', { params })

export const getSample = (id) => client.get(`/samples/${encodeURIComponent(id)}`)

export const createSample = (data) => client.post('/samples', data)

export const updateSample = (id, data) => client.put(`/samples/${encodeURIComponent(id)}`, data)

export const deleteSample = (id) => client.delete(`/samples/${encodeURIComponent(id)}`)

export const transferSample = (id, data) => client.put(`/samples/${encodeURIComponent(id)}/transfer`, data)

export const listSampleTransfers = (id) => client.get(`/samples/${encodeURIComponent(id)}/transfers`)