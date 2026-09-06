// ContextOS API client
const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const AUTH = { Authorization: 'Bearer example-token' }

async function req(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json', ...AUTH },
  }
  if (body) opts.body = JSON.stringify(body)
  const res = await fetch(`${BASE}${path}`, opts)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  if (res.status === 204) return null
  return res.json()
}

// Repositories
export const api = {
  repos: {
    list: (skip = 0, limit = 100) => req('GET', `/repositories?skip=${skip}&limit=${limit}`),
    get: (id) => req('GET', `/repositories/${id}`),
    create: (data) => req('POST', '/repositories', data),
    update: (id, data) => req('PATCH', `/repositories/${id}`, data),
    delete: (id) => req('DELETE', `/repositories/${id}`),
  },
  sessions: {
    list: (repoId, skip = 0, limit = 50) => req('GET', `/repositories/${repoId}/sessions?skip=${skip}&limit=${limit}`),
    get: (repoId, id) => req('GET', `/repositories/${repoId}/sessions/${id}`),
    create: (repoId, data) => req('POST', `/repositories/${repoId}/sessions`, data),
    update: (repoId, id, data) => req('PATCH', `/repositories/${repoId}/sessions/${id}`, data),
    delete: (repoId, id) => req('DELETE', `/repositories/${repoId}/sessions/${id}`),
  },
  tasks: {
    list: (repoId, skip = 0, limit = 100) => req('GET', `/repositories/${repoId}/tasks?skip=${skip}&limit=${limit}`),
    create: (repoId, data) => req('POST', `/repositories/${repoId}/tasks`, data),
    update: (repoId, id, data) => req('PATCH', `/repositories/${repoId}/tasks/${id}`, data),
    delete: (repoId, id) => req('DELETE', `/repositories/${repoId}/tasks/${id}`),
  },
  decisions: {
    list: (repoId, skip = 0, limit = 100) => req('GET', `/repositories/${repoId}/decisions?skip=${skip}&limit=${limit}`),
    create: (repoId, data) => req('POST', `/repositories/${repoId}/decisions`, data),
    update: (repoId, id, data) => req('PATCH', `/repositories/${repoId}/decisions/${id}`, data),
    delete: (repoId, id) => req('DELETE', `/repositories/${repoId}/decisions/${id}`),
  },
  memory: {
    get: (repoId) => req('GET', `/repositories/${repoId}/memory`),
    upsert: (repoId, data) => req('POST', `/repositories/${repoId}/memory`, data),
    update: (repoId, data) => req('PATCH', `/repositories/${repoId}/memory`, data),
  },
  bugs: {
    list: (repoId, skip = 0, limit = 100) => req('GET', `/repositories/${repoId}/bugs?skip=${skip}&limit=${limit}`),
    create: (repoId, data) => req('POST', `/repositories/${repoId}/bugs`, data),
    update: (repoId, id, data) => req('PATCH', `/repositories/${repoId}/bugs/${id}`, data),
    delete: (repoId, id) => req('DELETE', `/repositories/${repoId}/bugs/${id}`),
  },
  health: () => req('GET', '/api/health'),
}
