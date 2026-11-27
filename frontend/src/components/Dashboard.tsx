import { useState, useEffect, useCallback } from 'react'
import CommandCenter from './CommandCenter'
import GroupsView from './GroupsView'
import ProjectsView from './ProjectsView'
import TasksView from './TasksView'
import TenantSettings from './TenantSettings'
import UsersView from './UsersView'
import UserGuide from './UserGuide'

interface CompanyInfo {
  id?: number
  company_id?: number
  name?: string
}

interface WorkspaceProject {
  id: number
  name: string
  description?: string | null
  company_id: number
  group_id?: number | null
}

interface WorkspaceTask {
  id: number
  title: string
  description?: string | null
  status: string
  priority: string
  due_at?: string | null
  company_id: number
  project_id?: number | null
  assigned_to_id?: number | null
  assignee_name?: string | null
}

interface WorkspaceUser {
  id: number
  email: string
  role: string
  is_active: boolean
  company_id: number
}

interface WorkspaceGroup {
  id: number
  name: string
  description?: string | null
  company_id: number
  users?: WorkspaceUser[]
}

interface WorkspaceNotification {
  id: number | string
  title?: string
  message?: string
  is_read?: boolean
  created_at?: string
}

interface DashboardProps {
  companyData: CompanyInfo | null
  userRole: 'admin' | 'member'
  currentUserId?: number | null
  apiUrl?: string
  onLogout: () => void
}

export default function Dashboard({
  companyData,
  userRole,
  currentUserId = null,
  apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000',
  onLogout,
}: DashboardProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'groups' | 'projects' | 'tasks' | 'settings' | 'users' | 'guide'>('overview')
  
  // Shared Data States
  const [projects, setProjects] = useState<WorkspaceProject[]>([])
  const [tasks, setTasks] = useState<WorkspaceTask[]>([])
  const [users, setUsers] = useState<WorkspaceUser[]>([])
  const [groups, setGroups] = useState<WorkspaceGroup[]>([])
  const [notifications, setNotifications] = useState<WorkspaceNotification[]>([])
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [showNotifications, setShowNotifications] = useState(false)

  function getCsrfToken(): string {
    const match = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/)
    return match ? decodeURIComponent(match[1]) : ''
  }

  const loadWorkspaceData = useCallback(async () => {
    setLoading(true)
    setErrorMsg(null)
    try {
      const [pRes, tRes, uRes, gRes, nRes] = await Promise.all([
        fetch(`${apiUrl}/projects/`, { credentials: 'include' }),
        fetch(`${apiUrl}/tasks/`, { credentials: 'include' }),
        userRole === 'admin'
          ? fetch(`${apiUrl}/users/`, { credentials: 'include' }).catch(() => null)
          : Promise.resolve(null),
        fetch(`${apiUrl}/groups/`, { credentials: 'include' }).catch(() => null),
        fetch(`${apiUrl}/notifications/`, { credentials: 'include' }).catch(() => null),
      ])

      if (pRes.ok) setProjects(await pRes.json())
      if (tRes.ok) setTasks(await tRes.json())
      if (userRole === 'admin' && uRes && uRes.ok) {
        setUsers(await uRes.json())
      } else {
        setUsers([])
      }
      if (gRes && gRes.ok) setGroups(await gRes.json())
      if (nRes && nRes.ok) {
        const nData = await nRes.json()
        setNotifications(Array.isArray(nData) ? nData : [])
      }
    } catch {
      setErrorMsg('Failed to synchronize workspace data with Neon database. Check your authentication cookies.')
    } finally {
      setLoading(false)
    }
  }, [apiUrl, userRole])

  useEffect(() => {
    loadWorkspaceData()
  }, [loadWorkspaceData])

  // Live WebSocket Notification Listener (tenant comes from backend auth session)
  useEffect(() => {
    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let disposed = false
    let attempt = 0

    const connectSocket = () => {
      if (disposed) return
      const wsUrl = apiUrl.replace(/^http/, 'ws') + '/ws/notifications'
      socket = new WebSocket(wsUrl)

      socket.onopen = () => {
        attempt = 0
      }

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data)
          if (payload?.type === 'NOTIFICATION' && payload?.message) {
            setSuccessMsg(payload.message)
            setNotifications((prev) => [
              {
                id: payload.notification_id ?? Date.now(),
                title: payload.title || 'Live Alert',
                message: payload.message,
                created_at: new Date().toISOString(),
              },
              ...prev,
            ])
          }
        } catch {
          if (typeof event.data === 'string' && event.data.trim()) {
            setSuccessMsg(event.data)
          }
        }
      }

      socket.onclose = (event) => {
        if (disposed) return
        if (event.code === 1008) return
        const delayMs = Math.min(1000 * 2 ** attempt, 15000)
        attempt += 1
        reconnectTimer = window.setTimeout(connectSocket, delayMs)
      }
    }

    connectSocket()

    return () => {
      disposed = true
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
      }
      if (socket && socket.readyState <= WebSocket.OPEN) {
        socket.close()
      }
    }
  }, [apiUrl])

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#070b14', color: '#f8fafc', fontFamily: 'Inter, system-ui, sans-serif', overflow: 'hidden' }}>
      
      {/* Sidebar Navigation */}
      <aside style={{ width: '270px', background: '#0c1322', borderRight: '1px solid #1e293b', display: 'flex', flexDirection: 'column', padding: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '32px' }}>
          <div style={{ width: '42px', height: '42px', background: 'linear-gradient(135deg, #6366f1 0%, #3b82f6 50%, #06b6d4 100%)', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: '20px', color: 'white' }}>
            T
          </div>
          <div>
            <span style={{ fontWeight: 800, fontSize: '18px', color: 'white', display: 'block' }}>TaskFlow OS</span>
            <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 700, textTransform: 'uppercase' }}>{companyData?.name || 'Workspace'}</span>
          </div>
        </div>

        <nav style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
          <button onClick={() => setActiveTab('overview')} style={navBtnStyle(activeTab === 'overview')}>🏠 Command Center</button>
          <button onClick={() => setActiveTab('groups')} style={navBtnStyle(activeTab === 'groups')}>📁 Department Groups ({groups.length})</button>
          <button onClick={() => setActiveTab('projects')} style={navBtnStyle(activeTab === 'projects')}>⚡ Projects ({projects.length})</button>
          <button onClick={() => setActiveTab('tasks')} style={navBtnStyle(activeTab === 'tasks')}>📋 Task Operations ({tasks.length})</button>
          <button onClick={() => setActiveTab('users')} style={navBtnStyle(activeTab === 'users')}>👥 Personnel & Users ({users.length})</button>
          <button onClick={() => setActiveTab('settings')} style={navBtnStyle(activeTab === 'settings')}>⚙️ Tenant Settings</button>
          <button onClick={() => setActiveTab('guide')} style={navBtnStyle(activeTab === 'guide')}>📖 User Guide</button>
        </nav>

        <div style={{ borderTop: '1px solid #1e293b', paddingTop: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <button onClick={onLogout} style={{ width: '100%', background: 'rgba(239, 68, 68, 0.1)', color: '#f87171', border: '1px solid rgba(239, 68, 68, 0.3)', padding: '10px', borderRadius: '10px', fontWeight: 700, fontSize: '12px', cursor: 'pointer' }}>
            Logout Session
          </button>
        </div>
      </aside>

      {/* Main Panel */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#090d16' }}>
        <header style={{ height: '72px', background: '#0c1322', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 36px' }}>
          <h1 style={{ fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>
            {activeTab === 'overview' && 'Executive Command Center'}
            {activeTab === 'groups' && 'Department Groups & Unit Management'}
            {activeTab === 'projects' && 'Project Portfolios'}
            {activeTab === 'tasks' && 'Global Task Dispatcher'}
            {activeTab === 'users' && 'Personnel & User Management'}
            {activeTab === 'settings' && 'Tenant Configuration'}
            {activeTab === 'guide' && 'TaskFlow OS User Guide'}
          </h1>
          <div style={{ position: 'relative' }}>
            <button
              type="button"
              onClick={() => setShowNotifications((prev) => !prev)}
              style={{
                background: '#131d31',
                border: '1px solid #334155',
                color: '#38bdf8',
                padding: '8px 14px',
                borderRadius: '10px',
                fontSize: '12px',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              🔔 Notifications ({notifications.length})
            </button>

            {showNotifications && (
              <div
                style={{
                  position: 'absolute',
                  right: 0,
                  marginTop: '8px',
                  width: '350px',
                  maxHeight: '380px',
                  overflowY: 'auto',
                  background: '#0c1322',
                  border: '1px solid #1e293b',
                  borderRadius: '14px',
                  padding: '14px',
                  boxShadow: '0 20px 40px rgba(0, 0, 0, 0.65)',
                  zIndex: 999,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '10px',
                    paddingBottom: '8px',
                    borderBottom: '1px solid #1e293b',
                  }}
                >
                  <span style={{ fontSize: '13px', fontWeight: 800, color: '#f8fafc' }}>
                    Notifications ({notifications.length})
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowNotifications(false)}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: '#94a3b8',
                      fontSize: '14px',
                      cursor: 'pointer',
                    }}
                  >
                    ✕
                  </button>
                </div>

                {notifications.length === 0 ? (
                  <p style={{ fontSize: '12px', color: '#64748b', margin: 0 }}>
                    No notifications yet.
                  </p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {notifications.map((n, idx) => (
                      <div
                        key={n.id ?? idx}
                        style={{
                          background: '#131d31',
                          border: '1px solid #1e293b',
                          borderRadius: '10px',
                          padding: '10px 12px',
                        }}
                      >
                        <div style={{ fontSize: '12px', fontWeight: 700, color: '#38bdf8' }}>
                          {n.title || 'Notification'}
                        </div>
                        <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '3px' }}>
                          {n.message || ''}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </header>

        {(errorMsg || successMsg) && (
          <div style={{ padding: '12px 36px', background: errorMsg ? 'rgba(239, 68, 68, 0.12)' : 'rgba(34, 197, 94, 0.12)', borderBottom: `1px solid ${errorMsg ? '#ef4444' : '#22c55e'}`, color: errorMsg ? '#f87171' : '#4ade80', fontSize: '13px', fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>{errorMsg || successMsg}</span>
            <button onClick={() => { setErrorMsg(null); setSuccessMsg(null) }} style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', fontWeight: 800 }}>✕</button>
          </div>
        )}

        <div style={{ flex: 1, padding: '32px', overflowY: 'auto' }}>
          {loading ? (
            <div style={{ color: '#64748b', fontSize: '14px', textAlign: 'center', marginTop: '60px' }}>Loading Neon database records...</div>
          ) : (
            <>
              {activeTab === 'overview' && <CommandCenter groups={groups} projects={projects} tasks={tasks} users={users} />}
              {activeTab === 'groups' && <GroupsView groups={groups} projects={projects} tasks={tasks} users={users} userRole={userRole} apiUrl={apiUrl} getCsrfToken={getCsrfToken} refreshData={loadWorkspaceData} setSuccessMsg={setSuccessMsg} />}
              {activeTab === 'projects' && <ProjectsView projects={projects} groups={groups} tasks={tasks} userRole={userRole} currentUserId={currentUserId} apiUrl={apiUrl} getCsrfToken={getCsrfToken} refreshData={loadWorkspaceData} setSuccessMsg={setSuccessMsg} />}
{activeTab === 'tasks' && <TasksView tasks={tasks} users={users} projects={projects} userRole={userRole} currentUserId={currentUserId} apiUrl={apiUrl} getCsrfToken={getCsrfToken} refreshData={loadWorkspaceData} setSuccessMsg={setSuccessMsg} />}
              {activeTab === 'users' && <UsersView users={users} userRole={userRole} apiUrl={apiUrl} getCsrfToken={getCsrfToken} refreshData={loadWorkspaceData} setSuccessMsg={setSuccessMsg} />}
              {activeTab === 'settings' && <TenantSettings companyData={companyData} />}
              {activeTab === 'guide' && <UserGuide />}
            </>
          )}
        </div>
      </main>
    </div>
  )
}

const navBtnStyle = (isActive: boolean) => ({
  width: '100%',
  textAlign: 'left' as const,
  background: isActive ? '#1e293b' : 'transparent',
  color: isActive ? '#f8fafc' : '#94a3b8',
  border: 'none',
  padding: '12px 14px',
  borderRadius: '10px',
  fontWeight: 700,
  fontSize: '13px',
  cursor: 'pointer',
})