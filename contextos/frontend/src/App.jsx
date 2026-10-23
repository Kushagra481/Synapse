import { useEffect, useState } from 'react'
import { api } from './api'
import Repositories from './components/Repositories'
import Tasks from './components/Tasks'
import Memory from './components/Memory'
import Decisions from './components/Decisions'
import Sessions from './components/Sessions'
import Context from './components/Context'
import Evaluations from './components/Evaluations'
import Audit from './components/Audit'
import Members from './components/Members'
import Toast from './components/Toast'
import Login from './components/Login'
import { useToast } from './utils'

const navigation = [
  { id: 'overview', icon: '⌂', label: 'Overview' },
  { id: 'tasks', icon: '☷', label: 'Tasks' },
  { id: 'memory', icon: '◈', label: 'Project memory' },
  { id: 'decisions', icon: '◇', label: 'Decisions' },
  { id: 'sessions', icon: '◷', label: 'Agent sessions' },
  { id: 'context', icon: '↗', label: 'Agent handoff' },
  { id: 'evaluations', icon: '◎', label: 'Evaluations' },
  { id: 'audit', icon: '⌁', label: 'Audit trail' },
  { id: 'members', icon: '♙', label: 'Members' },
]

export default function App() {
  const [repo, setRepo] = useState(null)
  const [repoRole, setRepoRole] = useState(null)
  const [page, setPage] = useState('repositories')
  const [health, setHealth] = useState('checking')
  const [authReady, setAuthReady] = useState(false)
  const [authEnabled, setAuthEnabled] = useState(false)
  const [authConfigured, setAuthConfigured] = useState(false)
  const [authenticated, setAuthenticated] = useState(false)
  const { toasts, addToast } = useToast()

  useEffect(() => {
    const unauthorized = () => setAuthenticated(false)
    window.addEventListener('contextos:unauthorized', unauthorized)
    Promise.all([api.auth.status(), api.health()])
      .then(([authStatus]) => {
        setAuthEnabled(authStatus.enabled)
        setAuthConfigured(authStatus.configured)
        setAuthenticated(!authStatus.enabled || Boolean(api.auth.token()))
        setHealth('online')
      })
      .catch(() => {
        setHealth('offline')
        setAuthenticated(true)
      })
      .finally(() => setAuthReady(true))
    return () => window.removeEventListener('contextos:unauthorized', unauthorized)
  }, [])
  const selectRepo = value => {
    setRepo(value)
    setRepoRole('loading')
    setPage('overview')
    api.members.list(value.id)
      .then(result => setRepoRole(result.current_role))
      .catch(error => { setRepo(null); setRepoRole(null); setPage('repositories'); addToast(error.message, 'error') })
  }
  const signOut = () => { api.auth.logout(); setAuthenticated(false); setRepo(null); setRepoRole(null); setPage('repositories') }

  if (!authReady) return <div className="loading-wrap" style={{ minHeight: '100vh' }}><div className="spinner" /></div>
  if (authEnabled && !authenticated) {
    return <Login configured={authConfigured} onLogin={() => setAuthenticated(true)} />
  }

  const renderPage = () => {
    if (page === 'repositories') return <Repositories onSelect={selectRepo} />
    if (!repo) return <div className="empty-state"><div className="empty-state-icon">🗂️</div><h3>Choose a repository first</h3><p>Open a repository to work with its context.</p><button className="btn btn-primary" onClick={() => setPage('repositories')}>Browse repositories</button></div>
    if (repoRole === 'loading') return <div className="loading-wrap"><div className="spinner" /><span>Checking project access…</span></div>
    const canEdit = repoRole === 'owner' || repoRole === 'editor'
    if (page === 'overview') return <Overview repo={repo} onNavigate={setPage} repoRole={repoRole} />
    if (page === 'tasks') return <Tasks key={repo.id} repo={repo} canEdit={canEdit} />
    if (page === 'memory') return <Memory key={repo.id} repo={repo} addToast={addToast} canEdit={canEdit} />
    if (page === 'decisions') return <Decisions key={repo.id} repo={repo} addToast={addToast} canEdit={canEdit} />
    if (page === 'sessions') return <Sessions key={repo.id} repo={repo} addToast={addToast} canEdit={canEdit} />
    if (page === 'context') return <Context key={repo.id} repo={repo} addToast={addToast} canEdit={canEdit} />
    if (page === 'evaluations') return <Evaluations key={repo.id} repo={repo} addToast={addToast} canEdit={canEdit} />
    if (page === 'audit' && repoRole === 'owner') return <Audit key={repo.id} repo={repo} addToast={addToast} />
    if (page === 'members') return <Members key={repo.id} repo={repo} addToast={addToast} />
    return null
  }

  return <div className="layout">
    <aside className="sidebar">
      <div className="sidebar-logo"><div className="logo-icon">C</div><div className="logo-text">Context<span>OS</span></div></div>
      <div className="nav-section-label">Workspace</div>
      <nav className="sidebar-nav">
        <button className={'nav-item ' + (page === 'repositories' ? 'active' : '')} title="Repositories" aria-label="Repositories" onClick={() => setPage('repositories')}><span className="nav-icon">▦</span>Repositories</button>
        {repo && <>
          <div className="nav-section-label" title={repo.name}>{repo.name}</div>
          {navigation.filter(item => item.id !== 'audit' || repoRole === 'owner').map(item => <button key={item.id} className={'nav-item ' + (page === item.id ? 'active' : '')} title={item.label} aria-label={item.label} onClick={() => setPage(item.id)}><span className="nav-icon">{item.icon}</span>{item.label}</button>)}
        </>}
      </nav>
      <div className="sidebar-footer"><span className={'status-dot ' + (health === 'online' ? 'active' : health === 'offline' ? 'inactive' : 'idle')} /><div className="user-info"><div className="user-name">API {health}</div><div className="user-role">Local workspace</div></div></div>
    </aside>
    <main className="main">
       <header className="topbar"><div><div className="topbar-title">{repo?.name || 'Repositories'}</div><div className="topbar-sub">{repo ? `${repoRole && repoRole !== 'loading' ? `${repoRole} · ` : ''}${repo.local_path}` : 'Persistent memory for coding agents'}</div></div><div className="topbar-actions">{repo && <button className="btn btn-ghost btn-sm" onClick={() => { setRepo(null); setRepoRole(null); setPage('repositories') }}>Switch repository</button>}{authEnabled && <button className="btn btn-ghost btn-sm" onClick={signOut}>Sign out</button>}</div></header>
      <section className="content">{renderPage()}</section>
    </main>
    <Toast toasts={toasts} />
  </div>
}

function Overview({ repo, onNavigate, repoRole }) {
  const [data, setData] = useState({ tasks: [], decisions: [], sessions: [], memory: null })
  const [loading, setLoading] = useState(true)
  useEffect(() => { Promise.all([api.tasks.list(repo.id), api.decisions.list(repo.id), api.sessions.list(repo.id), api.memory.get(repo.id)]).then(([tasks, decisions, sessions, memory]) => setData({ tasks, decisions, sessions, memory })).catch(() => {}).finally(() => setLoading(false)) }, [repo.id])
  const cards = [{ icon: '☷', cls: 'cyan', value: data.tasks.length, label: 'Tracked tasks' }, { icon: '◇', cls: 'purple', value: data.decisions.length, label: 'Decisions saved' }, { icon: '◷', cls: 'green', value: data.sessions.length, label: 'Agent sessions' }, { icon: '↗', cls: 'amber', value: data.memory?.updated_at ? 'Ready' : 'Set up', label: 'Persistent memory' }]
  return <><div className="page-header"><div><h1 className="page-title">Project overview</h1><p className="page-subtitle">A compact record of what agents need to know about {repo.name}.</p></div><button className="btn btn-primary" onClick={() => onNavigate('context')}>Build agent handoff ↗</button></div>
    {loading ? <div className="loading-wrap"><div className="spinner" /></div> : <div className="stats-row">{cards.map(c => <div className="card stat-card" key={c.label}><div className={'stat-icon ' + c.cls}>{c.icon}</div><div><div className="stat-value">{c.value}</div><div className="stat-label">{c.label}</div></div></div>)}</div>}
     <div className="card" style={{ padding: 22, marginTop: 18 }}><h2 style={{ fontSize: 16, marginBottom: 8 }}>How the handoff works</h2><p className="page-subtitle" style={{ lineHeight: 1.7 }}>Record decisions, task status, and short session summaries once. The context endpoint assembles a task-specific, token-budgeted Markdown packet that works with any coding agent. Jev can optionally rank memories; a local relevance ranking is used when no TypeSafe key is configured.</p><div className="page-header-actions" style={{ marginTop: 18, justifyContent: 'flex-start', flexWrap: 'wrap' }}>{navigation.slice(1).filter(item => item.id !== 'audit' || repoRole === 'owner').map(item => <button key={item.id} className="btn btn-ghost" onClick={() => onNavigate(item.id)}>{item.icon} {item.label}</button>)}</div></div>
  </>
}
