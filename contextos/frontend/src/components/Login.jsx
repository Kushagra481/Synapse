import { useState } from 'react'
import { api } from '../api'

export default function Login({ configured, onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async event => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.auth.login({ username, password })
      setPassword('')
      onLogin()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 20, background: 'var(--bg-base)' }}>
    <section className="card" style={{ width: 'min(420px, 100%)', padding: 28 }}>
      <div className="sidebar-logo" style={{ padding: '0 0 20px', marginBottom: 22 }}>
        <div className="logo-icon">C</div><div className="logo-text">Context<span>OS</span></div>
      </div>
      <h1 className="page-title" style={{ fontSize: 20 }}>Sign in</h1>
      <p className="page-subtitle" style={{ marginBottom: 20 }}>Authenticate to access this workspace's repositories and saved context.</p>
      {!configured ? <div className="card" style={{ padding: 14, borderColor: 'rgba(245,158,11,.35)' }}>
        <strong style={{ color: 'var(--accent-amber)' }}>Authentication needs setup</strong>
        <p className="text-muted" style={{ marginTop: 7, lineHeight: 1.5 }}>Set AUTH_USERNAME, AUTH_PASSWORD_HASH, and a unique SECRET_KEY in the backend environment. Generate a password verifier with <span className="monospace">python -m app.auth_cli</span>.</p>
      </div> : <form onSubmit={submit}>
        <div className="form-group">
          <label className="form-label" htmlFor="login-username">Username</label>
          <input id="login-username" className="form-input" autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} required maxLength="255" />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="login-password">Password</label>
          <input id="login-password" className="form-input" type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required maxLength="1024" />
        </div>
        {error && <p role="alert" className="text-muted" style={{ color: 'var(--accent-red)', marginBottom: 14 }}>{error}</p>}
        <button className="btn btn-primary" type="submit" disabled={loading} style={{ width: '100%', justifyContent: 'center' }}>{loading ? 'Signing in…' : 'Sign in'}</button>
      </form>}
    </section>
  </main>
}
