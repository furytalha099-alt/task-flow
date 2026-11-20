import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { GoogleLogin } from '@react-oauth/google'
import type { CredentialResponse } from '@react-oauth/google'
import Dashboard from './components/Dashboard'

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [userRole, setUserRole] = useState<'admin' | 'member'>('admin')
  const [currentUserId, setCurrentUserId] = useState<number | null>(null)
  const [principalType, setPrincipalType] = useState<string>('company_admin')
  const [companyData, setCompanyData] = useState<any>(null)
  const [isCheckingSession, setIsCheckingSession] = useState(true)

  // Auth Mode: 'company_login' | 'user_login' | 'register_company'
  const [authMode, setAuthMode] = useState<'company_login' | 'user_login' | 'register_company'>('company_login')
  
  // Form Fields
  const [companyName, setCompanyName] = useState('')
  const [subdomain, setSubdomain] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  
  const [authError, setAuthError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  useEffect(() => {
    checkExistingSession()
  }, [])

  function getCsrfToken(): string {
    const match = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/)
    return match ? decodeURIComponent(match[1]) : ''
  }

  // Check active session using GET /companies/me
  async function checkExistingSession() {
    setIsCheckingSession(true)
    try {
      const res = await fetch(`${apiUrl}/companies/me`, { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        setCompanyData(data)
        setIsAuthenticated(true)
      } else {
        setIsAuthenticated(false)
      }
    } catch {
      setIsAuthenticated(false)
    } finally {
      setIsCheckingSession(false)
    }
  }

  // 1. Register Company: POST /companies/
  async function handleRegisterCompany(e: FormEvent) {
    e.preventDefault()
    setAuthError(null)
    setSuccessMessage(null)
    setIsSubmitting(true)

    const cleanSubdomain = subdomain.trim().toLowerCase().replace(/[^a-z0-9-]/g, '')

    try {
      const res = await fetch(`${apiUrl}/companies/`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: companyName.trim(),
          subdomain: cleanSubdomain,
          admin_email: email.trim(),
          admin_password: password,
        }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Failed to register company.')
      }

      setSuccessMessage('Company registered successfully! Please sign in as Company Admin.')
      setAuthMode('company_login')
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : 'Registration failed.')
    } finally {
      setIsSubmitting(false)
    }
  }

  // 2. Company Admin Login: POST /companies/login
  async function handleCompanyLogin(e: FormEvent) {
    e.preventDefault()
    setAuthError(null)
    setSuccessMessage(null)
    setIsSubmitting(true)

    try {
      const res = await fetch(`${apiUrl}/companies/login`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          admin_email: email.trim(),
          admin_password: password,
        }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Invalid admin email or password.')
      }

      const data = await res.json().catch(() => ({}))
      setUserRole('admin')
      setCurrentUserId(null)
      setPrincipalType('company_admin')
      setCompanyData(data.company || data)
      setIsAuthenticated(true)
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : 'Login failed.')
    } finally {
      setIsSubmitting(false)
    }
  }

  // 3. User Login: POST /users/login
  async function handleUserLogin(e: FormEvent) {
    e.preventDefault()
    setAuthError(null)
    setSuccessMessage(null)
    setIsSubmitting(true)

    try {
      const res = await fetch(`${apiUrl}/users/login`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim(),
          password: password,
        }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Invalid email or password.')
      }

      const data = await res.json().catch(() => ({}))
      const resolvedUserId =
        data?.user?.id ?? data?.user_id ?? data?.id ?? null
      setUserRole('member')
      setCurrentUserId(resolvedUserId != null ? Number(resolvedUserId) : null)
      setPrincipalType('user')
      setCompanyData(data.company || { name: 'Workspace User' })
      setIsAuthenticated(true)
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : 'User login failed.')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Google OAuth Login handler matching your backend POST /auth/google route
  async function handleGoogleSuccess(credentialResponse: CredentialResponse) {
    setAuthError(null)
    setSuccessMessage(null)

    if (!credentialResponse.credential) {
      setAuthError('Google credential missing.')
      return
    }

    try {
      const res = await fetch(`${apiUrl}/auth/google`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: credentialResponse.credential }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Google authentication failed.')
      }

      await checkExistingSession()
      setUserRole('admin')
      setPrincipalType('company_admin')
      setIsAuthenticated(true)
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : 'Google authentication failed.')
    }
  }

  // 4. Logout: POST /companies/logout or /users/logout
  async function handleLogout() {
    const logoutPath = principalType === 'user' ? '/users/logout' : '/companies/logout'
    try {
      const csrf = getCsrfToken()
      await fetch(`${apiUrl}${logoutPath}`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
      }).catch(() => null)
    } finally {
      setIsAuthenticated(false)
      setCurrentUserId(null)
      setCompanyData(null)
      setPassword('')
    }
  }

  if (isCheckingSession) {
    return (
      <div style={{ minHeight: '100vh', background: '#070b14', color: '#94a3b8', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Inter, system-ui, sans-serif' }}>
        Checking session...
      </div>
    )
  }

  if (isAuthenticated) {
    return (
      <Dashboard
        companyData={companyData}
        userRole={userRole}
        currentUserId={currentUserId}
        onLogout={handleLogout}
      />
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: '#070b14', color: '#f8fafc', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px', fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div style={{ width: '100%', maxWidth: '420px', background: '#0c1322', border: '1px solid #1e293b', borderRadius: '20px', padding: '32px' }}>
        <h1 style={{ fontSize: '22px', fontWeight: 800, marginBottom: '8px' }}>TaskFlow OS</h1>
        <p style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '20px' }}>
          {authMode === 'company_login' && 'Sign in to your Company Admin workspace.'}
          {authMode === 'user_login' && 'Sign in with your User account.'}
          {authMode === 'register_company' && 'Register a new company tenant.'}
        </p>

        <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
          <button type="button" onClick={() => { setAuthMode('company_login'); setAuthError(null) }} style={tabBtn(authMode === 'company_login')}>Admin Login</button>
          <button type="button" onClick={() => { setAuthMode('user_login'); setAuthError(null) }} style={tabBtn(authMode === 'user_login')}>User Login</button>
          <button type="button" onClick={() => { setAuthMode('register_company'); setAuthError(null) }} style={tabBtn(authMode === 'register_company')}>Register</button>
        </div>

        {authError && (
          <div style={{ background: 'rgba(239, 68, 68, 0.12)', border: '1px solid #ef4444', color: '#f87171', padding: '10px 12px', borderRadius: '10px', fontSize: '12px', marginBottom: '16px' }}>
            {authError}
          </div>
        )}

        {successMessage && (
          <div style={{ background: 'rgba(34, 197, 94, 0.12)', border: '1px solid #22c55e', color: '#4ade80', padding: '10px 12px', borderRadius: '10px', fontSize: '12px', marginBottom: '16px' }}>
            {successMessage}
          </div>
        )}

        {authMode === 'register_company' && (
          <form onSubmit={handleRegisterCompany} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <input type="text" required placeholder="Company Name" value={companyName} onChange={(e) => setCompanyName(e.target.value)} style={authInput} />
            <input type="text" required placeholder="Subdomain (e.g. acme)" value={subdomain} onChange={(e) => setSubdomain(e.target.value)} style={authInput} />
            <input type="email" required placeholder="Admin Email" value={email} onChange={(e) => setEmail(e.target.value)} style={authInput} />
            <input type="password" required placeholder="Admin Password" value={password} onChange={(e) => setPassword(e.target.value)} style={authInput} />
            <button type="submit" disabled={isSubmitting} style={authSubmitBtn}>
              {isSubmitting ? 'Registering...' : 'Register Company'}
            </button>
          </form>
        )}

        {authMode === 'company_login' && (
          <form onSubmit={handleCompanyLogin} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <input type="email" required placeholder="Admin Email" value={email} onChange={(e) => setEmail(e.target.value)} style={authInput} />
            <input type="password" required placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} style={authInput} />
            <button type="submit" disabled={isSubmitting} style={authSubmitBtn}>
              {isSubmitting ? 'Signing in...' : 'Sign In as Admin'}
            </button>
          </form>
        )}

        {authMode === 'user_login' && (
          <form onSubmit={handleUserLogin} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <input type="email" required placeholder="User Email" value={email} onChange={(e) => setEmail(e.target.value)} style={authInput} />
            <input type="password" required placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} style={authInput} />
            <button type="submit" disabled={isSubmitting} style={authSubmitBtn}>
              {isSubmitting ? 'Signing in...' : 'Sign In as User'}
            </button>
          </form>
        )}

        <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'center' }}>
          <GoogleLogin
            onSuccess={handleGoogleSuccess}
            onError={() => setAuthError('Google login failed.')}
          />
        </div>
      </div>
    </div>
  )
}

const tabBtn = (active: boolean) => ({
  flex: 1,
  padding: '8px',
  borderRadius: '8px',
  border: '1px solid #334155',
  background: active ? '#1e293b' : '#131d31',
  color: active ? '#f8fafc' : '#94a3b8',
  fontSize: '12px',
  fontWeight: 700,
  cursor: 'pointer',
})

const authInput = {
  width: '100%',
  background: '#131d31',
  border: '1px solid #334155',
  color: '#f8fafc',
  padding: '12px 14px',
  borderRadius: '10px',
  fontSize: '14px',
  outline: 'none',
  boxSizing: 'border-box' as const,
}

const authSubmitBtn = {
  background: 'linear-gradient(135deg, #6366f1 0%, #3b82f6 100%)',
  color: 'white',
  border: 'none',
  padding: '12px 18px',
  borderRadius: '10px',
  fontWeight: 700,
  fontSize: '13px',
  cursor: 'pointer',
}