import client from './client'

export const listIdeas = (params = {}) =>
  client.get('/ideas', { params: params.status ? { status: params.status } : {} })

export const getIdea = (id) => client.get(`/ideas/${encodeURIComponent(id)}`)

export const createIdea = (data) => client.post('/ideas', data)

export const updateIdeaStatus = (id, data) => client.put(`/ideas/${encodeURIComponent(id)}/status`, data)

export const parallelVerifyIdeas = (ideaIds) => client.post('/ideas/parallel_verify', { idea_ids: ideaIds })
