import client from './client'

export const login = (data) => client.post('/auth/login', data)
export const logout = () => client.post('/auth/logout')
export const getCurrentUser = () => client.get('/auth/me')
export const listUsers = () => client.get('/auth/users')
export const listUsersBrief = () => client.get('/auth/users/brief')
export const createUser = (data) => client.post('/auth/users', data)
export const updateUser = (id, data) => client.put(`/auth/users/${id}`, data)
export const deleteUser = (id) => client.delete(`/auth/users/${id}`)
export const updateMyDisciplines = (data) => client.put('/auth/me/disciplines', data)
