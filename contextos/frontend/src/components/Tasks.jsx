import { useState, useEffect } from 'react'
import { api } from '../api'
import { formatDateTime, useToast, truncate } from '../utils'
import Toast from './Toast'

const PRIORITY_BADGE = { high: 'badge-high', medium: 'badge-medium', low: 'badge-low' }
const STATUS_BADGE = { done: 'badge-done', in_progress: 'badge-in-progress', backlog: 'badge-backlog', blocked: 'badge-blocked' }

export default function Tasks({ repo }) {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const { toasts, addToast } = useToast()

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.tasks.list(repo.id)
      setTasks(Array.isArray(data) ? data : data?.items || [])
    } catch (e) { addToast(e.message, 'error') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [repo.id])

  const statuses = ['all', 'backlog', 'in_progress', 'done', 'blocked']
  const filtered = filter === 'all' ? tasks : tasks.filter(t => t.status === filter)

  const del = async (t) => {
    if (!confirm(`Delete "${t.title}"?`)) return
    try {
      await api.tasks.delete(repo.id, t.id)
      addToast('Task deleted')
      load()
    } catch (e) { addToast(e.message, 'error') }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Tasks</h1>
          <p className="page-subtitle">{repo.name}</p>
        </div>
        <button className="btn btn-primary" onClick={() => { setEditing(null); setShowModal(true) }}>＋ New Task</button>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        {statuses.map(s => (
          <button key={s} className={`btn btn-sm ${filter === s ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setFilter(s)}>
            {s === 'all' ? 'All' : s.replace('_', ' ')}
            <span style={{ marginLeft: 4, opacity: 0.7 }}>
              {s === 'all' ? tasks.length : tasks.filter(t => t.status === s).length}
            </span>
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading-wrap"><div className="spinner" /></div>
      ) : filtered.length === 0 ? (
        <div className="empty-state"><div className="empty-state-icon">✅</div><h3>No tasks</h3><p>Add your first task to track progress</p></div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Updated</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(t => (
                <tr key={t.id}>
                  <td>
                    <div style={{ fontWeight: 500 }}>{t.title}</div>
                    {t.description && <div className="text-muted" style={{ marginTop: 2 }}>{truncate(t.description, 60)}</div>}
                  </td>
                  <td><span className={`badge ${STATUS_BADGE[t.status] || 'badge-backlog'}`}>{t.status?.replace('_', ' ')}</span></td>
                  <td><span className={`badge ${PRIORITY_BADGE[t.priority] || ''}`}>{t.priority}</span></td>
                  <td className="text-muted">{formatDateTime(t.updated_at)}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button className="btn btn-ghost btn-sm" onClick={() => { setEditing(t); setShowModal(true) }}>✏️</button>
                      <button className="btn btn-danger btn-sm" onClick={() => del(t)}>🗑️</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <TaskModal
          repo={repo} task={editing}
          onClose={() => setShowModal(false)}
          onSaved={() => { setShowModal(false); load(); addToast(editing ? 'Task updated' : 'Task created') }}
          addToast={addToast}
        />
      )}
      <Toast toasts={toasts} />
    </div>
  )
}

function TaskModal({ repo, task, onClose, onSaved, addToast }) {
  const [form, setForm] = useState({
    title: task?.title || '', description: task?.description || '',
    status: task?.status || 'backlog', priority: task?.priority || 'medium',
    blocked_reason: task?.blocked_reason || ''
  })
  const [saving, setSaving] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const submit = async () => {
    if (!form.title.trim()) return addToast('Title is required', 'error')
    setSaving(true)
    try {
      if (task) await api.tasks.update(repo.id, task.id, form)
      else await api.tasks.create(repo.id, { ...form, repository_id: repo.id })
      onSaved()
    } catch (e) { addToast(e.message, 'error') }
    finally { setSaving(false) }
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-header">
          <h2 className="modal-title">{task ? 'Edit Task' : 'New Task'}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="form-group">
            <label className="form-label">Title *</label>
            <input className="form-input" value={form.title} onChange={e => set('title', e.target.value)} placeholder="Task title" />
          </div>
          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea className="form-textarea" value={form.description} onChange={e => set('description', e.target.value)} placeholder="What needs to be done?" />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="form-group">
              <label className="form-label">Status</label>
              <select className="form-select" value={form.status} onChange={e => set('status', e.target.value)}>
                <option value="backlog">Backlog</option>
                <option value="in_progress">In Progress</option>
                <option value="done">Done</option>
                <option value="blocked">Blocked</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Priority</label>
              <select className="form-select" value={form.priority} onChange={e => set('priority', e.target.value)}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
          </div>
          {form.status === 'blocked' && (
            <div className="form-group">
              <label className="form-label">Blocked reason</label>
              <input className="form-input" value={form.blocked_reason} onChange={e => set('blocked_reason', e.target.value)} placeholder="Why is this blocked?" />
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={submit} disabled={saving}>{saving ? 'Saving…' : 'Save Task'}</button>
        </div>
      </div>
    </div>
  )
}
