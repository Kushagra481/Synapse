import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Context({ repo, addToast }) {
  const [task, setTask] = useState('')
  const [budget, setBudget] = useState(4000)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [index, setIndex] = useState(null)
  const [indexing, setIndexing] = useState(false)
  const [query, setQuery] = useState('')
  const [searchProfile, setSearchProfile] = useState('hybrid')
  const [searchResults, setSearchResults] = useState(null)
  const [searching, setSearching] = useState(false)

  const refreshIndex = async () => {
    try {
      setIndex(await api.repos.index(repo.id))
    } catch (error) {
      addToast(error.message, 'error')
    }
  }

  useEffect(() => {
    refreshIndex()
  }, [repo.id])

  const ingest = async (fullReindex = false) => {
    setIndexing(true)
    try {
      const summary = await api.repos.ingest(repo.id, fullReindex)
      setIndex(await api.repos.index(repo.id))
      addToast(`Indexed ${summary.file_count} files and ${summary.symbol_count} symbols`)
    } catch (error) {
      addToast(error.message, 'error')
      await refreshIndex()
    } finally {
      setIndexing(false)
    }
  }

  const search = async () => {
    if (query.trim().length < 2) return addToast('Enter at least two characters to search', 'error')
    setSearching(true)
    try {
      setSearchResults(await api.repos.search(repo.id, query.trim(), 20, searchProfile))
    } catch (error) {
      addToast(error.message, 'error')
    } finally {
      setSearching(false)
    }
  }

  const generate = async () => {
    setLoading(true)
    try {
      setResult(await api.context(repo.id, { task, max_tokens: Number(budget) }))
    } catch (error) {
      addToast(error.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.text)
      addToast('Handoff copied')
    } catch {
      addToast('Clipboard permission was denied', 'error')
    }
  }

  const download = () => {
    const url = URL.createObjectURL(new Blob([result.text], { type: 'text/markdown' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = repo.name.toLowerCase().replace(/[^a-z0-9]+/g, '-') + '-handoff.md'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return <>
    <div className="page-header">
      <div>
        <h1 className="page-title">Repository context</h1>
        <p className="page-subtitle">Index code, search symbols, and build a task-specific agent handoff.</p>
      </div>
    </div>

    <section className="card" style={{ padding: 22, marginBottom: 18 }}>
      <div className="page-header" style={{ marginBottom: 12 }}>
        <div>
          <h2 style={{ fontSize: 16 }}>Code index</h2>
          <p className="page-subtitle">
            {index?.file_count
              ? `${index.file_count} files · ${index.symbol_count} symbols · ${index.import_count || 0} imports · ${index.ingestion_status}`
              : `Index status: ${index?.ingestion_status || 'checking…'}`}
          </p>
        </div>
        <div className="page-header-actions">
          <button className="btn btn-primary" onClick={() => ingest(false)} disabled={indexing}>
            {indexing ? 'Indexing…' : index?.file_count ? 'Refresh index' : 'Index repository'}
          </button>
          <button className="btn btn-ghost" onClick={() => ingest(true)} disabled={indexing}>
            Full re-index
          </button>
        </div>
      </div>
      {index?.indexed_commit_sha && <p className="text-muted">Indexed commit: <span className="monospace">{index.indexed_commit_sha.slice(0, 12)}</span> · {index.indexed_at ? new Date(index.indexed_at).toLocaleString() : ''}</p>}
      {index && <p className="text-muted" style={{ marginTop: 6 }}>Embeddings: {index.embedding_status || 'not configured'} ({index.embedding_count || 0}) · Graph sync: {index.graph_sync_status || 'pending'}</p>}
      {index?.working_tree_dirty && <p className="text-muted" style={{ color: 'var(--accent-amber)', marginTop: 6 }}>The working tree had local changes when this snapshot was indexed.</p>}
      {index?.skipped_count > 0 && <p className="text-muted" style={{ marginTop: 6 }}>{index.skipped_count} files were skipped by safety, size, binary, or ignore rules.</p>}
      {index?.ingestion_error && <p className="text-muted" style={{ color: 'var(--accent-red)', marginTop: 6 }}>{index.ingestion_error}</p>}
      <p className="text-muted" style={{ marginTop: 8 }}>Indexing is read-only, respects Git ignore rules, and excludes likely secrets and generated files.</p>
    </section>

    <section className="card" style={{ padding: 22, marginBottom: 18 }}>
      <h2 style={{ fontSize: 16, marginBottom: 12 }}>Search indexed code</h2>
      <div className="page-header-actions" style={{ justifyContent: 'flex-start' }}>
        <input
          className="form-input"
          aria-label="Search indexed code"
          placeholder="e.g. authentication middleware"
          value={query}
          onChange={event => setQuery(event.target.value)}
          onKeyDown={event => event.key === 'Enter' && search()}
        />
        <select className="form-input" aria-label="Retrieval profile" value={searchProfile} onChange={event => setSearchProfile(event.target.value)} style={{ width: 170 }}>
          <option value="hybrid">Hybrid retrieval</option>
          <option value="lexical">Lexical baseline</option>
          <option value="jev">Jev rerank (opt-in)</option>
        </select>
        <button className="btn btn-ghost" onClick={search} disabled={searching}>
          {searching ? 'Searching…' : 'Search'}
        </button>
      </div>
      {searchProfile === 'jev' && <p className="text-muted" style={{ marginTop: 8 }}>Jev sends bounded candidate snippets to TypeSafe only if the backend explicitly enables JEV_ALLOW_SOURCE_UPLOAD; otherwise search falls back to local ranking.</p>}
      {searchResults && <div style={{ marginTop: 16 }}>
        <p className="text-muted" style={{ marginBottom: 10 }}>{searchResults.total} matching symbols · {searchResults.retrieval?.profile || searchProfile}{searchResults.retrieval?.requested_profile === 'jev' ? ` (${searchResults.retrieval.jev_status})` : ''} · {searchResults.retrieval?.latency_ms?.toFixed(1)} ms</p>
        {searchResults.results.length === 0
          ? <p className="text-muted">No code matched. Index the repository or try different terms.</p>
          : searchResults.results.map((item, position) => <article className="card" key={`${item.file_path}:${item.start_line}:${position}`} style={{ padding: 14, marginBottom: 10 }}>
            <div className="page-header" style={{ marginBottom: 8 }}>
              <div>
                <strong>{item.qualified_name}</strong>
                <p className="text-muted monospace">{item.file_path}:{item.start_line}-{item.end_line}</p>
                <p className="text-muted" style={{ marginTop: 4 }}>Freshness: {item.freshness} · {Object.keys(item.ranking_signals || {}).join(' + ') || 'lexical signal'}</p>
              </div>
              <span className="badge badge-accepted">{item.relevance_score.toFixed(2)}</span>
            </div>
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 300, overflow: 'auto', background: 'var(--bg-elevated)', borderRadius: 8, padding: 12, fontSize: 12 }}>{item.source_text}</pre>
          </article>)}
      </div>}
    </section>

    <section className="card" style={{ padding: 22, marginBottom: 18 }}>
      <div className="form-group">
        <label className="form-label" htmlFor="task">What is the next agent working on?</label>
        <textarea id="task" className="form-textarea" rows="3" maxLength="6000" placeholder="e.g. Add OAuth login and update the settings screen" value={task} onChange={event => setTask(event.target.value)} />
      </div>
      <div className="page-header-actions" style={{ justifyContent: 'flex-start', flexWrap: 'wrap' }}>
        <label className="form-label" htmlFor="budget" style={{ margin: 0 }}>Token budget</label>
        <input id="budget" className="form-input" type="number" min="128" max="32000" step="256" style={{ width: 130 }} value={budget} onChange={event => setBudget(event.target.value)} />
        <button className="btn btn-primary" onClick={generate} disabled={loading}>{loading ? 'Building…' : 'Generate handoff'}</button>
      </div>
    </section>

    {result && <section className="card" style={{ padding: 22 }}>
      <div className="page-header">
        <div>
          <h2 style={{ fontSize: 16 }}>Ready to paste</h2>
          <p className="page-subtitle">{result.estimated_tokens.toLocaleString()} estimated tokens · {result.included_items} of {result.available_items} records · {result.jev_used ? 'Jev relevance ranking' : 'local relevance ranking'}</p>
        </div>
        <div className="page-header-actions">
          <button className="btn btn-ghost" onClick={download}>Download .md</button>
          <button className="btn btn-primary" onClick={copy}>Copy handoff</button>
        </div>
      </div>
      <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 560, overflow: 'auto', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 8, padding: 18, fontFamily: 'JetBrains Mono, monospace', fontSize: 12.5, lineHeight: 1.65, color: 'var(--text-secondary)' }}>{result.text}</pre>
      <p className="text-muted" style={{ marginTop: 10 }}>Token count is an estimate, not a model-specific tokenizer count. Saved memory summaries may be sent to Jev when configured. Code is scored locally by default; Jev code reranking and source embeddings each require separate server-side opt-in because they send bounded source snippets to external providers.</p>
    </section>}
  </>
}
