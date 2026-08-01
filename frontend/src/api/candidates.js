import client from './client'

export const listCandidates = (candidateType = '') =>
  client.get('/candidates', { params: candidateType ? { candidate_type: candidateType } : {} })

export const getCandidate = (candidateId) =>
  client.get(`/candidates/${candidateId}`)
