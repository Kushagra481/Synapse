import { useEffect, useState } from 'react'
import { api } from '../api'

const roleLabels = {
  owner: 'Owner',
  editor: 'Editor',
  viewer: 'Viewer',
}

export default function Members({ repo, addToast }) {
  const [members, setMembers] = useState([])
  const [currentRole, setCurrentRole] = useState(null)
  const [username, setUsername] = useState('')
  const [role, setRole] = useState('viewer')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    try {
      const result = await api.members.list(repo.id)
      setMembers(result.items || [])
      setCurrentRole(result.current_role)
    } catch (error) {
      addToast(error.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [repo.id])

  const addMember = async event => {
    event.preventDefault()
    if (!username.trim()) return
    setSaving(true)
    try {
      await api.members.add(repo.id, { username: username.trim(), role })
      setUsername('')
      await load()
      addToast('Member added')
    } catch (error) {
      addToast(error.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const changeRole = async (member, nextRole) => {
    try {
      await api.members.update(repo.id, member.username, { role: nextRole })
      await load()
      addToast('Member role updated')
    } catch (error) {
      addToast(error.message, 'error')
    }
  }

  const removeMember = async member => {
    if (!window.confirm(`Remove ${member.username} from ${repo.name}?`)) return
    try {
      await api.members.remove(repo.id, member.username)
      await load()
      addToast('Member removed')
    } catch (error) {
      addToast(error.message, 'error')
    }
  }

  const canManage = currentRole === 'owner'

  return <>
    <div className="page-header">
      <div>
        <h1 className="page-title">Project members</h1>
        <p className="page-subtitle">Share this repository’s saved context with other configured workspace accounts.</p>
      </div>
    </div>
    {canManage && <form className="card" onSubmit={addMember} style={{ padding: 20, marginBottom: 18 }}>
      <h2 style={{ fontSize: 16, marginBottom: 14 }}>Add a member</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(140px, 1fr) auto', gap: 12, alignItems: 'end' }}>
        <div className="form-group" style={{ flex: 2, marginBottom: 0 }}>
          <label className="form-label" htmlFor="member-username">Configured username</label>
          <input id="member-username" className="form-input" value={username} onChange={event => setUsername(event.target.value)} maxLength={255} placeholder="teammate" />
        </div>
        <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
          <label className="form-label" htmlFor="member-role">Role</label>
          <select id="member-role" className="form-input" value={role} onChange={event => setRole(event.target.value)}>
            <option value="viewer">Viewer</option>
            <option value="editor">Editor</option>
          </select>
        </div>
        <button className="btn btn-primary" type="submit" disabled={saving || !username.trim()}>{saving ? 'Adding…' : 'Add member'}</button>
      </div>
      <p className="text-muted" style={{ marginTop: 12 }}>Accounts must first be added by the workspace operator in AUTH_USERS_JSON. The owner role cannot be granted or transferred here.</p>
    </form>}
    {!canManage && <div className="card" style={{ padding: 16, marginBottom: 18 }}>
      <span className="text-muted">Your role: <strong>{roleLabels[currentRole] || currentRole || 'Member'}</strong></span>
    </div>}
    {loading ? <div className="loading-wrap"><div className="spinner" /></div> :
      <div className="card table-wrap"><table className="data-table">
        <thead><tr><th>Account</th><th>Role</th>{canManage && <th>Actions</th>}</tr></thead>
        <tbody>{members.map(member => <tr key={member.username}>
          <td>{member.username}</td>
          <td>{canManage && member.role !== 'owner'
            ? <select className="form-input" style={{ maxWidth: 150 }} value={member.role} onChange={event => changeRole(member, event.target.value)}>
                <option value="viewer">Viewer</option>
                <option value="editor">Editor</option>
              </select>
            : roleLabels[member.role] || member.role}</td>
          {canManage && <td>{member.role !== 'owner' && <button className="btn btn-ghost btn-sm" onClick={() => removeMember(member)}>Remove</button>}</td>}
        </tr>)}</tbody>
      </table></div>}
  </>
}
