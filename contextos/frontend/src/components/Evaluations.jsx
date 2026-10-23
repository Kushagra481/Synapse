import { useEffect, useState } from 'react'
import { api } from '../api'

const metrics = [
  ['precision_at_k', 'Precision@k'],
  ['recall_at_k', 'Recall@k'],
  ['mrr', 'MRR'],
  ['ndcg_at_k', 'nDCG@k'],
  ['provenance_coverage', 'Source provenance'],
  ['freshness_coverage', 'Freshness verified'],
  ['jev_used', 'Jev used'],
]

const labels = value => value.split(/\n|,/).map(item => item.trim()).filter(Boolean)
const percent = value => `${Math.round((value || 0) * 100)}%`

export default function Evaluations({ repo, addToast, canEdit = false }) {
  const [cases, setCases] = useState([])
  const [runs, setRuns] = useState([])
  const [latest, setLatest] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [includeJev, setIncludeJev] = useState(false)
  const [form, setForm] = useState({ name: '', query: '', expected_files: '', expected_symbols: '' })

  const refresh = async () => {
    const [caseRows, runRows] = await Promise.all([
      api.evaluations.cases(repo.id),
      api.evaluations.runs(repo.id),
    ])
    setCases(caseRows)
    setRuns(runRows)
    if (runRows.length) {
      try { setLatest(await api.evaluations.getRun(repo.id, runRows[0].id)) } catch {}
    }
  }

  useEffect(() => {
    refresh().catch(error => addToast(error.message, 'error')).finally(() => setLoading(false))
  }, [repo.id])

  const createCase = async event => {
    event.preventDefault()
    if (!form.expected_files.trim() && !form.expected_symbols.trim()) {
      addToast('Add at least one expected file or symbol so the benchmark can score retrieval.', 'error')
      return
    }
    setSaving(true)
    try {
      await api.evaluations.createCase(repo.id, {
        name: form.name.trim(),
        query: form.query.trim(),
        expected_files: labels(form.expected_files),
        expected_symbols: labels(form.expected_symbols),
      })
      setForm({ name: '', query: '', expected_files: '', expected_symbols: '' })
      await refresh()
      addToast('Benchmark case saved')
    } catch (error) {
      addToast(error.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const deleteCase = async item => {
    try {
      await api.evaluations.deleteCase(repo.id, item.id)
      await refresh()
      addToast('Benchmark case removed')
    } catch (error) {
      addToast(error.message, 'error')
    }
  }

  const run = async () => {
    setRunning(true)
    try {
      const profiles = includeJev ? ['lexical', 'hybrid', 'jev'] : ['lexical', 'hybrid']
      const result = await api.evaluations.run(repo.id, { profiles, top_k: 10 })
      setLatest(result)
      await refresh()
      addToast('Retrieval benchmark completed')
    } catch (error) {
      addToast(error.message, 'error')
    } finally {
      setRunning(false)
    }
  }

  return <>
    <div className="page-header">
      <div>
        <h1 className="page-title">Retrieval evaluations</h1>
        <p className="page-subtitle">Save real repository questions and compare hybrid retrieval with a lexical baseline.</p>
      </div>
    </div>
    {canEdit && <div className="page-header-actions" style={{ justifyContent: 'flex-end', marginBottom: 16 }}>
      <label className="text-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input type="checkbox" checked={includeJev} onChange={event => setIncludeJev(event.target.checked)} />
        Include Jev reranking
      </label>
      <button className="btn btn-primary" onClick={run} disabled={running || cases.length === 0}>
        {running ? 'Running…' : 'Run benchmark'}
      </button>
    </div>}
    {includeJev && <p className="text-muted" style={{ margin: '-8px 0 16px', textAlign: 'right' }}>Jev reranking sends code snippets to TypeSafe only when JEV_ALLOW_SOURCE_UPLOAD=true and a key is configured; otherwise it records a local fallback.</p>}

    <div className="card" style={{ padding: 20, marginBottom: 18 }}>
      <strong>How to read these scores</strong>
      <p className="text-muted" style={{ marginTop: 7, lineHeight: 1.6 }}>
        Add questions agents actually ask and label the files or symbols that should answer them. Precision, recall, MRR, and nDCG are retrieval metrics; token counts and latency are estimates/measurements from this run, not guaranteed savings.
      </p>
    </div>

    {canEdit && <section className="card" style={{ padding: 20, marginBottom: 18 }}>
      <h2 style={{ fontSize: 16, marginBottom: 14 }}>Add a benchmark case</h2>
      <form onSubmit={createCase}>
        <div className="form-group">
          <label className="form-label" htmlFor="eval-name">Case name</label>
          <input id="eval-name" className="form-input" required minLength="2" maxLength="255" value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} placeholder="Find the authentication middleware" />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="eval-query">Question an agent would ask</label>
          <textarea id="eval-query" className="form-textarea" required minLength="2" maxLength="3000" rows="2" value={form.query} onChange={event => setForm({ ...form, query: event.target.value })} placeholder="Where is user authentication verified?" />
        </div>
        <div className="card-grid" style={{ marginBottom: 14 }}>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label" htmlFor="eval-files">Expected file paths</label>
            <textarea id="eval-files" className="form-textarea" rows="2" value={form.expected_files} onChange={event => setForm({ ...form, expected_files: event.target.value })} placeholder="backend/app/auth.py" />
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label" htmlFor="eval-symbols">Expected symbol names</label>
            <textarea id="eval-symbols" className="form-textarea" rows="2" value={form.expected_symbols} onChange={event => setForm({ ...form, expected_symbols: event.target.value })} placeholder="verify_user_token" />
          </div>
        </div>
        <button className="btn btn-ghost" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save case'}</button>
      </form>
    </section>}

    {loading ? <div className="loading-wrap"><div className="spinner" /></div> : <section className="card" style={{ padding: 20, marginBottom: 18 }}>
      <div className="page-header" style={{ marginBottom: 14 }}>
        <div><h2 style={{ fontSize: 16 }}>Cases</h2><p className="text-muted">{cases.length} saved question{cases.length === 1 ? '' : 's'}</p></div>
      </div>
      {!cases.length ? <p className="text-muted">No cases yet. Add a few questions with expected file paths or symbol names, then run the benchmark.</p> :
        <div style={{ display: 'grid', gap: 9 }}>{cases.map(item => <div key={item.id} className="card" style={{ padding: 13, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 14 }}>
          <div><strong>{item.name}</strong><p className="text-muted" style={{ marginTop: 4 }}>{item.query}</p><p className="text-muted monospace" style={{ marginTop: 5 }}>{[...item.expected_files, ...item.expected_symbols].join(' · ')}</p></div>
           {canEdit && <button className="btn btn-danger btn-sm" onClick={() => deleteCase(item)} aria-label={`Delete ${item.name}`}>Remove</button>}
        </div>)}</div>}
    </section>}

    {latest && <section className="card" style={{ padding: 20, marginBottom: 18 }}>
      <div className="page-header">
        <div><h2 style={{ fontSize: 16 }}>Latest run</h2><p className="text-muted">{latest.case_count} cases · top {latest.top_k} · index {latest.index_commit_sha?.slice(0, 12) || 'unknown'} · {new Date(latest.created_at).toLocaleString()}</p></div>
        <span className="badge badge-accepted">{latest.latency_ms.toFixed(0)} ms total</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 650 }}>
          <thead><tr>{['Profile', ...metrics.map(([, label]) => label), 'Avg latency'].map(label => <th key={label} style={{ textAlign: 'left', padding: '9px 8px', borderBottom: '1px solid var(--border)', color: 'var(--text-secondary)', fontSize: 12 }}>{label}</th>)}</tr></thead>
          <tbody>{Object.entries(latest.metrics).map(([profile, values]) => <tr key={profile}>
            <td style={{ padding: '10px 8px', borderBottom: '1px solid var(--border)', fontWeight: 600 }}>{profile}</td>
            {metrics.map(([key]) => <td key={key} style={{ padding: '10px 8px', borderBottom: '1px solid var(--border)' }}>{percent(values[key])}</td>)}
            <td style={{ padding: '10px 8px', borderBottom: '1px solid var(--border)' }}>{values.retrieval_latency_ms.toFixed(1)} ms</td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="text-muted" style={{ marginTop: 12 }}>Estimated tokens across this run: {latest.estimated_tokens.toLocaleString()}. Results are tied to the indexed commit shown above; runs are saved for comparison.</p>
      <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>{latest.case_results.map((item, index) => <details key={`${item.case_id}-${item.profile}-${index}`} className="card" style={{ padding: 12 }}>
        <summary style={{ cursor: 'pointer', fontWeight: 600 }}>{item.case_name} · {item.profile} · MRR {item.metrics.mrr.toFixed(2)}{item.profile === 'jev' ? ` · ${item.retrieval.jev_status}` : ''}</summary>
        <p className="text-muted" style={{ margin: '8px 0' }}>{item.query}</p>
        {item.retrieved.length ? <ul style={{ paddingLeft: 18 }}>{item.retrieved.map((row, rowIndex) => <li key={`${row.file_path}-${row.start_line}-${rowIndex}`} className="text-muted" style={{ margin: '5px 0' }}><span className="monospace">{row.file_path}:{row.start_line}-{row.end_line}</span> · {row.qualified_name} · {row.freshness}</li>)}</ul> : <p className="text-muted">No results returned.</p>}
      </details>)}</div>
    </section>}
  </>
}
