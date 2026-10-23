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
  const [facts, setFacts] = useState([])
  const [factForm, setFactForm] = useState({ title: '', content: '', topic_key: '', fact_type: 'project', source_type: 'manual', source_ref: '', source_file_path: '', confidence: 0.75, verified: false, supersedes_fact_id: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savingFact, setSavingFact] = useState(false)
  const loadFacts = () => api.memory.facts(repo.id, true).then(setFacts)
  useEffect(() => { Promise.all([api.memory.get(repo.id), loadFacts()]).then(([memory]) => setForm(memory)).catch(e => addToast(e.message, 'error')).finally(() => setLoading(false)) }, [repo.id])
  const save = async () => { setSaving(true); try { const result = await api.memory.update(repo.id, Object.fromEntries(fields.map(([key]) => [key, form[key] || null]))); setForm(result); addToast('Project memory saved') } catch (e) { addToast(e.message, 'error') } finally { setSaving(false) } }
  const saveFact = async event => {
    event.preventDefault()
    setSavingFact(true)
    try {
      const payload = { ...factForm, confidence: Number(factForm.confidence), source_ref: factForm.source_ref || null }
      if (factForm.source_type !== 'repository_file') payload.source_file_path = null
      if (!factForm.supersedes_fact_id) delete payload.supersedes_fact_id
      await api.memory.createFact(repo.id, payload)
      setFactForm({ title: '', content: '', topic_key: '', fact_type: 'project', source_type: 'manual', source_ref: '', source_file_path: '', confidence: 0.75, verified: false, supersedes_fact_id: '' })
      await loadFacts()
      addToast('Fact saved with provenance')
    } catch (e) { addToast(e.message, 'error') } finally { setSavingFact(false) }
  }
  const removeFact = async fact => {
    if (!window.confirm(`Archive “${fact.title}”? The fact will be hidden from new handoffs but retained for history.`)) return
    try { await api.memory.deleteFact(repo.id, fact.id); await loadFacts(); addToast('Fact archived') } catch (e) { addToast(e.message, 'error') }
  }
  if (loading) return <div className="loading-wrap"><div className="spinner" /></div>
  return <><div className="page-header"><div><h1 className="page-title">Project memory</h1><p className="page-subtitle">Durable facts and instructions shared across agent sessions.</p></div><button className="btn btn-primary" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save memory'}</button></div><div className="card" style={{ padding: 22, marginBottom: 18 }}>{fields.map(([key, label, placeholder]) => <div className="form-group" key={key}><label className="form-label" htmlFor={key}>{label}</label><textarea id={key} className="form-textarea" rows={key === 'custom_notes' ? 7 : 3} placeholder={placeholder} value={form[key] || ''} onChange={e => setForm(old => ({ ...old, [key]: e.target.value }))} /></div>)}<p className="text-muted">Only saved summaries and structured project records go into agent handoffs. Raw conversation transcripts are not included.</p></div>
    <section className="card" style={{ padding: 22, marginBottom: 18 }}>
      <h2 style={{ fontSize: 16, marginBottom: 6 }}>Provenance-backed facts</h2>
      <p className="text-muted" style={{ marginBottom: 16 }}>Facts can cite an indexed file and commit. Conflicts and stale source-backed facts are kept out of new handoffs until corrected.</p>
      <form onSubmit={saveFact}>
        <div className="card-grid" style={{ marginBottom: 12 }}>
          <div className="form-group" style={{ marginBottom: 0 }}><label className="form-label" htmlFor="fact-title">Title</label><input id="fact-title" className="form-input" required minLength="2" maxLength="255" value={factForm.title} onChange={e => setFactForm(old => ({ ...old, title: e.target.value }))} /></div>
          <div className="form-group" style={{ marginBottom: 0 }}><label className="form-label" htmlFor="fact-topic">Topic key</label><input id="fact-topic" className="form-input" required minLength="2" maxLength="255" value={factForm.topic_key} onChange={e => setFactForm(old => ({ ...old, topic_key: e.target.value }))} placeholder="auth-architecture" /></div>
        </div>
        <div className="form-group"><label className="form-label" htmlFor="fact-content">Fact</label><textarea id="fact-content" className="form-textarea" required minLength="2" maxLength="12000" rows="3" value={factForm.content} onChange={e => setFactForm(old => ({ ...old, content: e.target.value }))} /></div>
        <div className="card-grid" style={{ marginBottom: 12 }}>
          <div className="form-group" style={{ marginBottom: 0 }}><label className="form-label" htmlFor="fact-source-type">Source type</label><select id="fact-source-type" className="form-input" value={factForm.source_type} onChange={e => setFactForm(old => ({ ...old, source_type: e.target.value }))}>{['manual', 'session', 'repository_file', 'decision', 'task'].map(type => <option key={type}>{type}</option>)}</select></div>
          <div className="form-group" style={{ marginBottom: 0 }}><label className="form-label" htmlFor="fact-confidence">Confidence (0–1)</label><input id="fact-confidence" className="form-input" type="number" min="0" max="1" step="0.05" value={factForm.confidence} onChange={e => setFactForm(old => ({ ...old, confidence: e.target.value }))} /></div>
        </div>
        {factForm.source_type === 'repository_file' && <div className="form-group"><label className="form-label" htmlFor="fact-file">Indexed file path</label><input id="fact-file" className="form-input monospace" required maxLength="1024" value={factForm.source_file_path} onChange={e => setFactForm(old => ({ ...old, source_file_path: e.target.value }))} placeholder="backend/app/auth.py" /></div>}
        <div className="form-group"><label className="form-label" htmlFor="fact-ref">Source reference (optional)</label><input id="fact-ref" className="form-input" maxLength="2000" value={factForm.source_ref} onChange={e => setFactForm(old => ({ ...old, source_ref: e.target.value }))} placeholder="Session, decision, or issue reference" /></div>
        <div className="form-group"><label className="form-label" htmlFor="fact-replaces">Supersede an existing fact (optional)</label><select id="fact-replaces" className="form-input" value={factForm.supersedes_fact_id} onChange={e => setFactForm(old => ({ ...old, supersedes_fact_id: e.target.value, topic_key: e.target.value ? (facts.find(fact => fact.id === e.target.value)?.topic_key || old.topic_key) : old.topic_key }))}><option value="">No — detect topic conflicts</option>{facts.filter(fact => !fact.superseded_by_id && fact.conflict_status !== 'superseded').map(fact => <option key={fact.id} value={fact.id}>{fact.topic_key} — {fact.title}</option>)}</select></div>
        <label className="text-muted" style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '12px 0' }}><input type="checkbox" checked={factForm.verified} onChange={e => setFactForm(old => ({ ...old, verified: e.target.checked }))} />I verified this fact against its source</label>
        <button className="btn btn-ghost" type="submit" disabled={savingFact}>{savingFact ? 'Saving…' : 'Save fact'}</button>
      </form>
      <div style={{ display: 'grid', gap: 10, marginTop: 20 }}>{facts.length === 0 ? <p className="text-muted">No structured facts yet.</p> : facts.map(fact => <article className="card" key={fact.id} style={{ padding: 14 }}>
        <div className="page-header" style={{ marginBottom: 8 }}><div><strong>{fact.title}</strong><p className="text-muted" style={{ marginTop: 4 }}>{fact.content}</p></div><button className="btn btn-danger btn-sm" onClick={() => removeFact(fact)}>Archive</button></div>
        <p className="text-muted monospace">{fact.topic_key} · {fact.source_type}{fact.source_file_path ? ` · ${fact.source_file_path}` : ''}{fact.source_commit_sha ? ` · ${fact.source_commit_sha.slice(0, 10)}` : ''}</p>
        <p className="text-muted" style={{ marginTop: 4 }}>Confidence {fact.confidence.toFixed(2)} · {fact.verified ? 'verified' : 'unverified'} · {fact.conflict_status}{fact.is_stale ? ' · stale source' : ''}</p>
        {fact.conflicts_with?.length > 0 && <p className="text-muted" style={{ color: 'var(--accent-amber)', marginTop: 4 }}>Conflicts with {fact.conflicts_with.length} fact(s); excluded from handoffs pending review.</p>}
      </article>)}</div>
    </section>
  </>
}
