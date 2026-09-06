import { useState, useEffect } from 'react'
import { api } from '../api'
import { useToast } from '../utils'
import Toast from './Toast'

export default function Repositories({ onSelect }) {
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showModal, setShowModal] = useState(false)
  const { toasts, addToast } = useToast()

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.repos.list()
      setRepos(Array.isArray(data) ? data : data?.items || [])
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const filtered = repos.filter(r =>
    r.name?.toLowerCase().includes(search.toLowerCase()) ||
    r.url?.toLowerCase().includes(search.toLowerCase())
  )

  const techColors = ['#00d9ff', '#7c3aed', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']
  const getTechColor = (i) => techColors[i % techColors.length]

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Repositories</h1>
          <p className="page-subtitle">Manage your AI-powered project memory</p>
        </div>
        <div className="page-header-actions">
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>＋ New Repository</button>
        </div>
      </div>

      <div className="stats-row">
        {[
          { icon: '🗂️', cls: 'cyan', val: repos.length, label: 'Total Repos' },
          { icon: '⚡', cls: 'green', val: repos.filter(r => r.is_active).length, label: 'Active' },
          { icon: '🔗', cls: 'purple', val: repos.reduce((s, r) => s + (r.session_count || 0), 0), label: 'Sessions' },
          { icon: '✅', cls: 'amber', val: repos.reduce((s, r) => s + (r.task_count || 0), 0), label: 'Tasks' },
        ].map(({ icon, cls, val, label }) => (
          <div className="card stat-card" key={label}>
            <div className={`stat-icon ${cls}`}>{icon}</div>
            <div>
              <div className="stat-value">{val}</div>
              <div className="stat-label">{label}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginBottom: 16 }}>
        <div className="search-wrap" style={{ maxWidth: '100%' }}>
          <span className="search-icon">🔍</span>
          <input className="search-input" placeholder="Search repositories..." value={search} onChange={e => setSearch(e.target.value)} />
        </div>
      </div>

      {loading ? (
        <div className="loading-wrap"><div className="spinner" /><span>Loading repositories…</span></div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">🗂️</div>
          <h3>{search ? 'No matches found' : 'No repositories yet'}</h3>
          <p>{search ? 'Try a different search term' : 'Add your first repository to get started'}</p>
        </div>
      ) : (
        <div className="card-grid">
          {filtered.map((repo, ri) => (
            <div className="card repo-card" key={repo.id} onClick={() => onSelect(repo)}>
              <div className="repo-card-header">
                <div>
                  <div className="repo-card-title">{repo.name}</div>
                  {repo.url && <div className="repo-card-url truncate">{repo.url}</div>}
                </div>
                <span className={`status-badge ${repo.is_active ? 'active' : 'inactive'}`}>
                  <span className={`status-dot ${repo.is_active ? 'active' : 'inactive'}`} />
                  {repo.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>
              <div className="repo-card-body">
                {repo.description && <p className="repo-description">{repo.description}</p>}
                {repo.tech_stack?.length > 0 && (
                  <div className="tech-tags">
                    {repo.tech_stack.slice(0, 5).map((t, i) => (
                      <span className="tech-tag" key={i} style={{ color: getTechColor(i), borderColor: getTechColor(i) + '44' }}>
                        {typeof t === 'string' ? t : t.name}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="repo-card-footer">
                <div className="repo-stats">
                  <span className="repo-stat">💬 <strong>{repo.session_count ?? 0}</strong> sessions</span>
                  <span className="repo-stat">✅ <strong>{repo.task_count ?? 0}</strong> tasks</span>
                </div>
                <span className="text-muted">{new Date(repo.created_at).toLocaleDateString()}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {showModal && <AddRepoModal onClose={() => setShowModal(false)} onCreated={() => { setShowModal(false); load(); addToast('Repository created!') }} addToast={addToast} />}
      <Toast toasts={toasts} />
    </div>
  )
}

function AddRepoModal({ onClose, onCreated, addToast }) {
  const [form, setForm] = useState({ name: '', url: '', description: '', primary_language: '' })
  const [saving, setSaving] = useState(false)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const submit = async () => {
    if (!form.name.trim()) return addToast('Name is required', 'error')
    setSaving(true)
    try {
      await api.repos.create({ ...form })
      onCreated()
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-header">
          <h2 className="modal-title">New Repository</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="form-group">
            <label className="form-label">Name *</label>
            <input className="form-input" placeholder="my-awesome-project" value={form.name} onChange={e => set('name', e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Repository URL</label>
            <input className="form-input" placeholder="https://github.com/user/repo" value={form.url} onChange={e => set('url', e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Primary Language</label>
            <input className="form-input" placeholder="Python, TypeScript…" value={form.primary_language} onChange={e => set('primary_language', e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea className="form-textarea" placeholder="What does this project do?" value={form.description} onChange={e => set('description', e.target.value)} />
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={submit} disabled={saving}>{saving ? 'Creating…' : 'Create Repository'}</button>
        </div>
      </div>
    </div>
  )
}
