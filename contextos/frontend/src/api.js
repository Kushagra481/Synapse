const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const TOKEN_KEY = 'contextos_access_token'

async function req(method, path, body) {
  const opts = { method, headers: {} }
  const token = typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(TOKEN_KEY)
  if (token) opts.headers.Authorization = 'Bearer ' + token
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  let res
  try { res = await fetch(BASE + path, opts) }
  catch { throw new Error('Cannot reach ContextOS API. Check that the backend is running and VITE_API_URL is correct.') }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    if (res.status === 401 && path !== '/auth/login') {
      if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem(TOKEN_KEY)
      window.dispatchEvent(new Event('contextos:unauthorized'))
    }
    throw new Error(typeof err.detail === 'string' ? err.detail : 'Request failed (' + res.status + ')')
  }
  if (res.status === 204) return null
  return res.json()
}
const list = (path) => req('GET', path).then(data => Array.isArray(data) ? data : data?.items || [])

export const api = {
  auth: {
    token: () => typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(TOKEN_KEY),
    status: () => req('GET', '/auth/status'),
    login: async data => {
      const result = await req('POST', '/auth/login', data)
      if (typeof sessionStorage !== 'undefined') sessionStorage.setItem(TOKEN_KEY, result.access_token)
      return result
    },
    logout: () => {
      if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem(TOKEN_KEY)
    },
  },
  repos: {
    list: (skip = 0, limit = 100) => req('GET', '/repositories?skip=' + skip + '&limit=' + limit),
    get: id => req('GET', '/repositories/' + id),
    create: data => req('POST', '/repositories', data),
    update: (id, data) => req('PATCH', '/repositories/' + id, data),
    delete: id => req('DELETE', '/repositories/' + id),
    index: id => req('GET', '/repositories/' + id + '/index'),
    ingest: (id, fullReindex = false) => req('POST', '/repositories/' + id + '/ingest?full_reindex=' + fullReindex),
    search: (id, query, limit = 20, profile = 'hybrid') => req('GET', '/repositories/' + id + '/code/search?q=' + encodeURIComponent(query) + '&limit=' + limit + '&profile=' + encodeURIComponent(profile)),
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
    facts: (repoId, includeStale = true) => req('GET', '/repositories/' + repoId + '/memory/facts?include_stale=' + includeStale),
    createFact: (repoId, data) => req('POST', '/repositories/' + repoId + '/memory/facts', data),
    deleteFact: (repoId, factId) => req('DELETE', '/repositories/' + repoId + '/memory/facts/' + factId),
  },
  evaluations: {
    cases: repoId => list('/repositories/' + repoId + '/evaluations/cases'),
    createCase: (repoId, data) => req('POST', '/repositories/' + repoId + '/evaluations/cases', data),
    deleteCase: (repoId, caseId) => req('DELETE', '/repositories/' + repoId + '/evaluations/cases/' + caseId),
    runs: repoId => list('/repositories/' + repoId + '/evaluations/runs'),
    run: (repoId, data) => req('POST', '/repositories/' + repoId + '/evaluations/runs', data),
    getRun: (repoId, runId) => req('GET', '/repositories/' + repoId + '/evaluations/runs/' + runId),
  },
  audit: { list: (repoId, params = '') => req('GET', '/repositories/' + repoId + '/audit-events' + params) },
  members: {
    list: repoId => req('GET', '/repositories/' + repoId + '/members'),
    add: (repoId, data) => req('POST', '/repositories/' + repoId + '/members', data),
    update: (repoId, username, data) => req('PATCH', '/repositories/' + repoId + '/members/' + encodeURIComponent(username), data),
    remove: (repoId, username) => req('DELETE', '/repositories/' + repoId + '/members/' + encodeURIComponent(username)),
  },
  context: (repoId, data) => req('POST', '/repositories/' + repoId + '/context', data),
  health: () => req('GET', '/api/health'),
}
