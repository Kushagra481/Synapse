export default function Toast({ toasts = [] }) {
  if (!toasts.length) return null
  return <div className="toast-container" role="status" aria-live="polite">{toasts.map(toast => <div className={'toast ' + (toast.type || 'success')} key={toast.id}><span>{toast.type === 'error' ? '!' : '✓'}</span>{toast.msg}</div>)}</div>
}
