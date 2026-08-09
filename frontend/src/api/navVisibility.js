import client from './client'

export const getNavVisibility = () => client.get('/nav-visibility')

export const updateNavVisibility = (data) => client.put('/nav-visibility', data)