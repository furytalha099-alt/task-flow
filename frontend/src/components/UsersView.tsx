import { useState } from 'react'

export default function UsersView({ users, userRole, apiUrl, getCsrfToken, refreshData, setSuccessMsg }: any) {
  const [showModal, setShowModal] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('member')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  async function handleRegisterUser(e: React.FormEvent) {
    e.preventDefault()
    setErrorMsg(null)
    if (!email.trim() || !password.trim()) return

    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/users/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          password: password.trim(),
          role: role,
        }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        const errorMessage = typeof errData.detail === 'string' 
          ? errData.detail 
          : JSON.stringify(errData.detail) || 'Failed to register user.'
        throw new Error(errorMessage)
      }

      setSuccessMsg(`User ${email} created successfully!`)
      setEmail('')
      setPassword('')
      setRole('member')
      setShowModal(false)
      await refreshData()
    } catch (err: any) {
      setErrorMsg(err.message || 'Error creating user.')
    }
  }

  async function handleDeleteUser(userId: number, userEmail: string) {
    if (!confirm(`Are you sure you want to delete user ${userEmail}? Their sessions will be revoked.`)) return

    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/users/${userId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Failed to delete user.')
      }

      setSuccessMsg(`User ${userEmail} deleted successfully.`)
      await refreshData()
    } catch (err: any) {
      alert(err.message || 'Error deleting user.')
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#f8fafc' }}>Company Personnel Management</h2>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '2px' }}>Register employee accounts and manage access credentials.</p>
        </div>
        {userRole === 'admin' ? (
          <button
            onClick={() => setShowModal(true)}
            style={{ background: 'linear-gradient(135deg, #6366f1 0%, #3b82f6 100%)', color: 'white', border: 'none', padding: '10px 18px', borderRadius: '10px', fontWeight: 700, fontSize: '13px', cursor: 'pointer', boxShadow: '0 4px 15px rgba(99, 102, 241, 0.4)' }}
          >
            + Register New User
          </button>
        ) : (
          <span style={{ fontSize: '12px', color: '#64748b', fontStyle: 'italic' }}>Administrator rights required to manage personnel.</span>
        )}
      </div>

      {errorMsg && (
        <div style={{ padding: '12px 16px', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid #ef4444', borderRadius: '10px', color: '#f87171', fontSize: '13px' }}>
          {errorMsg}
        </div>
      )}

      {/* Users Table / Grid */}
      <div style={{ background: '#0c1322', border: '1px solid #1e293b', borderRadius: '20px', padding: '24px', boxShadow: '0 4px 20px rgba(0,0,0,0.3)' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#f8fafc', marginBottom: '16px' }}>Active Personnel ({users.length})</h3>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {users.length === 0 ? (
            <div style={{ color: '#64748b', fontSize: '14px', padding: '12px 0' }}>
              {userRole === 'admin' ? 'No personnel accounts registered yet.' : 'Access restricted or no users found.'}
            </div>
          ) : (
            users.map((u: any) => (
              <div key={u.id} style={{ background: '#131d31', border: '1px solid #1e293b', borderRadius: '12px', padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                  <div style={{ width: '38px', height: '38px', background: '#1e293b', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#38bdf8', fontWeight: 800, fontSize: '14px', border: '1px solid #334155' }}>
                    {u.email[0].toUpperCase()}
                  </div>
                  <div>
                    <div style={{ fontSize: '15px', fontWeight: 700, color: '#f8fafc' }}>{u.email}</div>
                    <div style={{ fontSize: '12px', color: '#94a3b8', display: 'flex', gap: '8px', alignItems: 'center', marginTop: '2px' }}>
                      <span>ID: <strong style={{ color: '#38bdf8' }}>#{u.id}</strong></span>
                      <span>•</span>
                      <span>Role: <strong style={{ textTransform: 'uppercase', color: u.role === 'admin' ? '#38bdf8' : '#cbd5e1' }}>{u.role}</strong></span>
                      <span>•</span>
                      <span>Status: <strong style={{ color: u.is_active ? '#22c55e' : '#ef4444' }}>{u.is_active ? 'Active' : 'Deactivated'}</strong></span>
                    </div>
                  </div>
                </div>

                {userRole === 'admin' && (
                  <button
                    onClick={() => handleDeleteUser(u.id, u.email)}
                    style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', border: 'none', padding: '8px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 700, cursor: 'pointer' }}
                  >
                    Revoke & Delete
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Register User Modal */}
      {showModal && (
        <div style={modalOverlayStyle}>
          <div style={modalContentStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>Register Employee Account</h2>
              <button onClick={() => setShowModal(false)} style={{ background: 'transparent', border: 'none', color: '#94a3b8', fontSize: '18px', cursor: 'pointer' }}>✕</button>
            </div>
            <form onSubmit={handleRegisterUser} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>EMPLOYEE EMAIL</label>
                <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="user@company.com" style={inputStyle} />
              </div>
              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>TEMPORARY PASSWORD</label>
                <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 6 characters..." style={inputStyle} />
              </div>
              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>ACCESS ROLE</label>
                <select value={role} onChange={(e) => setRole(e.target.value)} style={inputStyle}>
                  <option value="member">Regular Member</option>
                  <option value="admin">Administrator</option>
                </select>
              </div>
              <button type="submit" style={primaryBtnStyle}>Create Account</button>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

const inputStyle = {
  width: '100%',
  background: '#131d31',
  border: '1px solid #334155',
  color: '#f8fafc',
  padding: '12px 14px',
  borderRadius: '10px',
  marginTop: '6px',
  outline: 'none',
  fontSize: '14px',
  boxSizing: 'border-box' as const,
}

const primaryBtnStyle = {
  background: 'linear-gradient(135deg, #6366f1 0%, #3b82f6 100%)',
  color: 'white',
  border: 'none',
  padding: '12px 18px',
  borderRadius: '10px',
  fontWeight: 700,
  fontSize: '13px',
  cursor: 'pointer',
  boxShadow: '0 4px 15px rgba(99, 102, 241, 0.4)',
}

const modalOverlayStyle = {
  position: 'fixed' as const,
  inset: 0,
  background: 'rgba(7, 11, 20, 0.8)',
  backdropFilter: 'blur(4px)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
  padding: '20px',
}

const modalContentStyle = {
  width: '100%',
  maxWidth: '480px',
  background: '#0c1322',
  border: '1px solid #1e293b',
  borderRadius: '24px',
  padding: '32px',
  boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)',
}