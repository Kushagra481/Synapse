const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

async function req(method, path, body) {
  const opts = { method, headers: {} }
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  let res
  try { res = await fetch(BASE + path, opts) }
  catch { throw new Error('Cannot reach ContextOS API. Check that the backend is running and VITE_API_URL is correct.') }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(typeof err.detail === 'string' ? err.detail : 'Request failed (' + res.status + ')')
  }
  if (res.status === 204) return null
  return res.json()
}
const list = (path) => req('GET', path).then(data => Array.isArray(data) ? data : data?.items || [])

export const api = {
  repos: {
    list: (skip = 0, limit = 100) => req('GET', '/repositories?skip=' + skip + '&limit=' + limit),
    get: id => req('GET', '/repositories/' + id),
    create: data => req('POST', '/repositories', data),
    update: (id, data) => req('PATCH', '/repositories/' + id, data),
    delete: id => req('DELETE', '/repositories/' + id),
    index: id => req('GET', '/repositories/' + id + '/index'),
    ingest: (id, fullReindex = false) => req('POST', '/repositories/' + id + '/ingest?full_reindex=' + fullReindex),
    search: (id, query, limit = 20) => req('GET', '/repositories/' + id + '/code/search?q=' + encodeURIComponent(query) + '&limit=' + limit),
  },
  sessions: {
    list: (repoId) => list('/repositories/' + repoId + '/sessions'),
    get: (repoId, id) => req('GET', '/repositories/' + repoId + '/sessions/' + id),
    create: (repoId, data) => req('POST', '/repositories/' + repoId + '/sessions', data),
    update: (repoId, id, data) => req('PATCH', '/repositories/' + repoId + '/sessions/' + id, data),
    delete: (repoId, id) => req('DELETE', '/repositories/' + repoId + '/sessions/' + id),
    addNote: (repoId, sessionId, data) => req('POST', '/repositories/' + repoId + '/sessions/' + sessionId + '/conversations', { ...data, repository_id: repoId, session_id: sessionId }),
  },
  tasks: {
    list: repoId => list('/repositories/' + repoId + '/tasks'),
    create: (repoId, data) => req('POST', '/repositories/' + repoId + '/tasks', data),
    update: (repoId, id, data) => req('PATCH', '/repositories/' + repoId + '/tasks/' + id, data),
    delete: (repoId, id) => req('DELETE', '/repositories/' + repoId + '/tasks/' + id),
  },
  decisions: {
    list: repoId => list('/repositories/' + repoId + '/decisions'),
    create: (repoId, data) => req('POST', '/repositories/' + repoId + '/decisions', { ...data, repository_id: repoId }),
    update: (repoId, id, data) => req('PATCH', '/repositories/' + repoId + '/decisions/' + id, data),
    delete: (repoId, id) => req('DELETE', '/repositories/' + repoId + '/decisions/' + id),
  },
  memory: {
    get: repoId => req('GET', '/repositories/' + repoId + '/memory'),
    upsert: (repoId, data) => req('POST', '/repositories/' + repoId + '/memory', { ...data, repository_id: repoId }),
    update: (repoId, data) => req('PATCH', '/repositories/' + repoId + '/memory', data),
  },
  context: (repoId, data) => req('POST', '/repositories/' + repoId + '/context', data),
  health: () => req('GET', '/api/health'),
}
