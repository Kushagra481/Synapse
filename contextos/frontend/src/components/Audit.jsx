import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Audit({ repo, addToast }) {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    api.audit.list(repo.id, '?limit=200')
      .then(setEvents)
      .catch(error => addToast(error.message, 'error'))
      .finally(() => setLoading(false))
  }, [repo.id])

  return <>
    <div className="page-header">
      <div><h1 className="page-title">Audit trail</h1><p className="page-subtitle">Recent authenticated actions for this repository. Request bodies, prompts, and credentials are not recorded.</p></div>
    </div>
    {loading ? <div className="loading-wrap"><div className="spinner" /></div> : events.length === 0
      ? <div className="empty-state"><div className="empty-state-icon">◷</div><h3>No audit events yet</h3><p>Repository actions will appear here after they are made.</p></div>
      : <div className="card table-wrap"><table className="data-table"><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Result</th><th>Duration</th></tr></thead><tbody>{events.map(event => <tr key={event.id}>
        <td>{new Date(event.created_at).toLocaleString()}</td>
        <td>{event.actor}</td>
        <td className="monospace">{event.action}</td>
        <td><span className={'badge ' + (event.outcome === 'success' ? 'badge-done' : 'badge-blocked')}>{event.status_code} {event.outcome}</span></td>
        <td>{event.duration_ms.toFixed(1)} ms</td>
      </tr>)}</tbody></table></div>}
  </>
}
