import { useEffect, useState } from 'react'
import { api } from '../api'

const fields = [
  ['project_goal', 'Project goal', 'What are we building and for whom?'],
  ['architecture_summary', 'Architecture', 'Key components and how they fit together.'],
  ['current_task', 'Current task', 'What is actively being worked on?'],
  ['custom_notes', 'Agent instructions and notes', 'Conventions, constraints, and context agents should keep.'],
]
export default function Memory({ repo, addToast }) {
  const [form, setForm] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  useEffect(() => { api.memory.get(repo.id).then(setForm).catch(e => addToast(e.message, 'error')).finally(() => setLoading(false)) }, [repo.id])
  const save = async () => { setSaving(true); try { const result = await api.memory.update(repo.id, Object.fromEntries(fields.map(([key]) => [key, form[key] || null]))); setForm(result); addToast('Project memory saved') } catch (e) { addToast(e.message, 'error') } finally { setSaving(false) } }
  if (loading) return <div className="loading-wrap"><div className="spinner" /></div>
  return <><div className="page-header"><div><h1 className="page-title">Project memory</h1><p className="page-subtitle">Durable facts and instructions shared across agent sessions.</p></div><button className="btn btn-primary" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save memory'}</button></div><div className="card" style={{ padding: 22 }}>{fields.map(([key, label, placeholder]) => <div className="form-group" key={key}><label className="form-label" htmlFor={key}>{label}</label><textarea id={key} className="form-textarea" rows={key === 'custom_notes' ? 7 : 3} placeholder={placeholder} value={form[key] || ''} onChange={e => setForm(old => ({ ...old, [key]: e.target.value }))} /></div>)}<p className="text-muted">Only saved summaries and structured project records go into agent handoffs. Raw conversation transcripts are not included.</p></div></>
}
