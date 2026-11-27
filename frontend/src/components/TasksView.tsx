import { useState } from 'react'
import { TaskAISummaryCard } from './TaskAISummaryCard'

interface TaskRecord {
  id: number
  title: string
  description?: string | null
  status?: string
  priority?: string
  assigned_to_id?: number | null
  project_id?: number | null
}

interface UserRecord {
  id: number
  email: string
}

interface ProjectRecord {
  id: number
  name: string
}

interface TasksViewProps {
  tasks: TaskRecord[]
  users: UserRecord[]
  projects: ProjectRecord[]
  userRole: 'admin' | 'member'
  currentUserId?: number | null
  apiUrl: string
  getCsrfToken: () => string
  refreshData: () => void
  setSuccessMsg: (msg: string | null) => void
}

export default function TasksView({ tasks, users, projects, userRole, currentUserId, apiUrl, getCsrfToken, refreshData, setSuccessMsg }: TasksViewProps) {
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [taskTitle, setTaskTitle] = useState('')
  const [taskDesc, setTaskDesc] = useState('')
  const [taskPriority, setTaskPriority] = useState('normal')
  const [assignedUserId, setAssignedUserId] = useState<string>('')
  const [projectId, setProjectId] = useState<string>('')

  // State for editing an existing task
  const [editingTask, setEditingTask] = useState<TaskRecord | null>(null)
  const [editTaskTitle, setEditTaskTitle] = useState('')
  const [editTaskDesc, setEditTaskDesc] = useState('')
  const [editTaskPriority, setEditTaskPriority] = useState('normal')
  const [editAssignedUserId, setEditAssignedUserId] = useState<string>('')
  const [editProjectId, setEditProjectId] = useState<string>('')

  async function handleCreateTask(e: React.FormEvent) {
    e.preventDefault()
    if (!taskTitle.trim()) return

    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/tasks/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        body: JSON.stringify({
          title: taskTitle.trim(),
          description: taskDesc.trim() || null,
          priority: taskPriority,
          assigned_to_id: assignedUserId ? Number(assignedUserId) : null,
          project_id: projectId ? Number(projectId) : null,
        })
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Failed to create task')
      }

      setSuccessMsg('Task dispatched successfully!')
      setTaskTitle('')
      setTaskDesc('')
      setTaskPriority('normal')
      setAssignedUserId('')
      setProjectId('')
      setShowCreateModal(false)
      refreshData()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Error updating task.')
    }
  }

  async function handleUpdateTask(e: React.FormEvent) {
    e.preventDefault()
    if (!editingTask || !editTaskTitle.trim()) return

    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/tasks/${editingTask.id}`, {
        method: 'PUT',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        body: JSON.stringify({
          title: editTaskTitle.trim(),
          description: editTaskDesc.trim() || null,
          priority: editTaskPriority,
          status: editingTask.status || 'todo',
          assigned_to_id: editAssignedUserId ? Number(editAssignedUserId) : null,
          project_id: editProjectId ? Number(editProjectId) : null,
        })
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Failed to update task')
      }

      setSuccessMsg('Task updated successfully!')
      setEditingTask(null)
      refreshData()
    } catch (err: any) {
      alert(err.message || 'Error updating task.')
    }
  }

  function openEditModal(task: TaskRecord) {
    setEditingTask(task)
    setEditTaskTitle(task.title || '')
    setEditTaskDesc(task.description || '')
    setEditTaskPriority(task.priority || 'normal')
    setEditAssignedUserId(task.assigned_to_id ? String(task.assigned_to_id) : '')
    setEditProjectId(task.project_id ? String(task.project_id) : '')
  }

  async function handleUpdateTaskStatus(taskId: number, newStatus: string) {
  try {
    const csrf = getCsrfToken()
    const res = await fetch(`${apiUrl}/tasks/${taskId}/status`, {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
      },
      body: JSON.stringify({ status: newStatus })
    })

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      throw new Error(errData.detail || 'Failed to update task status')
    }

    setSuccessMsg(`Task status updated to ${newStatus}.`)
    refreshData()
  } catch (err: unknown) {
    alert(err instanceof Error ? err.message : 'Error updating task status.')
  }
}

  async function handleDeleteTask(taskId: number) {
    if (!confirm('Are you sure you want to permanently delete this task?')) return

    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/tasks/${taskId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        }
      })

      if (!res.ok) throw new Error('Failed to delete task')

      setSuccessMsg('Task deleted successfully.')
      refreshData()
    } catch {
      alert('Error deleting task.')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#f8fafc' }}>Global Task Dispatcher</h2>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '2px' }}>Track, dispatch, and execute actionable deliverables across projects and personnel.</p>
        </div>
        {userRole === 'admin' && (
          <button 
            onClick={() => setShowCreateModal(true)}
            style={{ background: 'linear-gradient(135deg, #6366f1 0%, #3b82f6 100%)', color: 'white', border: 'none', padding: '10px 18px', borderRadius: '10px', fontWeight: 700, fontSize: '13px', cursor: 'pointer', boxShadow: '0 4px 15px rgba(99, 102, 241, 0.4)' }}
          >
            + Dispatch New Task
          </button>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {tasks.length === 0 ? (
          <div style={{ background: '#0c1322', border: '1px solid #1e293b', padding: '32px', borderRadius: '20px', color: '#64748b', fontSize: '14px', textAlign: 'center' }}>
            No tasks registered in the Neon database yet. Create your first task above!
          </div>
        ) : (
          tasks.map((task) => {
            const assignee = users.find((u) => u.id === task.assigned_to_id)
            const associatedProject = projects.find((p) => p.id === task.project_id)
            
            return (
              <div 
                key={task.id} 
                style={{ background: '#0c1322', border: '1px solid #1e293b', borderRadius: '16px', padding: '22px', display: 'flex', flexDirection: 'column', gap: '14px', boxShadow: '0 4px 20px rgba(0,0,0,0.3)' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '16px', flexWrap: 'wrap' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1, minWidth: '260px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                      <h3 style={{ fontSize: '16px', fontWeight: 800, color: '#f8fafc' }}>{task.title}</h3>
                      <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 700, background: '#131d31', padding: '2px 8px', borderRadius: '6px' }}>ID #{task.id}</span>
                      {associatedProject && (
                        <span style={{ fontSize: '10px', color: '#818cf8', fontWeight: 700, background: 'rgba(99, 102, 241, 0.15)', padding: '2px 8px', borderRadius: '6px' }}>Project: {associatedProject.name}</span>
                      )}
                    </div>
                    <p style={{ fontSize: '13px', color: '#94a3b8' }}>{task.description || 'No description provided.'}</p>
                    <div style={{ fontSize: '12px', color: '#64748b', display: 'flex', gap: '12px', alignItems: 'center', marginTop: '4px' }}>
                      <span>Assignee: <strong style={{ color: '#38bdf8' }}>{assignee?.email || `User ID #${task.assigned_to_id || 'Unassigned'}`}</strong></span>
                      <span>•</span>
                      <span>Priority: <span style={{ textTransform: 'uppercase', color: '#cbd5e1', fontWeight: 600 }}>{task.priority || 'normal'}</span></span>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexShrink: 0 }}>
                    <select 
                      value={task.status || 'todo'} 
                      onChange={(e) => handleUpdateTaskStatus(task.id, e.target.value)}
                      style={{ background: '#131d31', border: '1px solid #334155', color: task.status === 'done' ? '#22c55e' : '#38bdf8', padding: '8px 12px', borderRadius: '8px', fontSize: '12px', fontWeight: 700, outline: 'none', cursor: 'pointer' }}
                    >
                      <option value="todo">To Do</option>
                      <option value="in_progress">In Progress</option>
                      <option value="done">Done</option>
                    </select>

                    {userRole === 'admin' && (
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button 
                          onClick={() => openEditModal(task)}
                          style={{ background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: 'none', padding: '8px 12px', borderRadius: '8px', fontSize: '12px', fontWeight: 700, cursor: 'pointer' }}
                        >
                          Edit
                        </button>
                        <button 
                          onClick={() => handleDeleteTask(task.id)}
                          style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', border: 'none', padding: '8px 12px', borderRadius: '8px', fontSize: '12px', fontWeight: 700, cursor: 'pointer' }}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                <TaskAISummaryCard
                  task={task}
                  currentUserId={currentUserId}
                  userRole={userRole}
                  apiBaseUrl={apiUrl}
                />
              </div>
            )
          })
        )}
      </div>

      {/* Create Task Modal */}
      {showCreateModal && (
        <div style={modalOverlayStyle}>
          <div style={modalContentStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>Dispatch New Task</h2>
              <button onClick={() => setShowCreateModal(false)} style={{ background: 'transparent', border: 'none', color: '#94a3b8', fontSize: '18px', cursor: 'pointer' }}>✕</button>
            </div>
            <form onSubmit={handleCreateTask} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>TASK TITLE</label>
                <input type="text" required value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} placeholder="e.g. Implement backend API endpoint" style={inputStyle} />
              </div>

              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>ASSIGN TO PROJECT</label>
                <select value={projectId} onChange={(e) => setProjectId(e.target.value)} style={inputStyle}>
                  <option value="">-- None / Independent Task --</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>ASSIGN TO USER</label>
                  <select value={assignedUserId} onChange={(e) => setAssignedUserId(e.target.value)} style={inputStyle}>
                    <option value="">-- Unassigned --</option>
                    {users.map((u) => (
                      <option key={u.id} value={u.id}>{u.email}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>PRIORITY LEVEL</label>
                  <select value={taskPriority} onChange={(e) => setTaskPriority(e.target.value)} style={inputStyle}>
                    <option value="low">Low</option>
                    <option value="normal">Normal</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>DESCRIPTION</label>
                <textarea value={taskDesc} onChange={(e) => setTaskDesc(e.target.value)} placeholder="Task guidelines..." style={{ ...inputStyle, height: '90px', resize: 'vertical' }} />
              </div>

              <button type="submit" style={primaryBtnStyle}>Dispatch Task</button>
            </form>
          </div>
        </div>
      )}

      {/* Edit Task Modal */}
      {editingTask && (
        <div style={modalOverlayStyle}>
          <div style={modalContentStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>Edit Task #{editingTask.id}</h2>
              <button onClick={() => setEditingTask(null)} style={{ background: 'transparent', border: 'none', color: '#94a3b8', fontSize: '18px', cursor: 'pointer' }}>✕</button>
            </div>
            <form onSubmit={handleUpdateTask} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>TASK TITLE</label>
                <input type="text" required value={editTaskTitle} onChange={(e) => setEditTaskTitle(e.target.value)} style={inputStyle} />
              </div>

              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>ASSIGN TO PROJECT</label>
                <select value={editProjectId} onChange={(e) => setEditProjectId(e.target.value)} style={inputStyle}>
                  <option value="">-- None / Independent Task --</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>ASSIGN TO USER</label>
                  <select value={editAssignedUserId} onChange={(e) => setEditAssignedUserId(e.target.value)} style={inputStyle}>
                    <option value="">-- Unassigned --</option>
                   {users.map((u) => (
                      <option key={u.id} value={u.id}>{u.email}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>PRIORITY LEVEL</label>
                  <select value={editTaskPriority} onChange={(e) => setEditTaskPriority(e.target.value)} style={inputStyle}>
                    <option value="low">Low</option>
                    <option value="normal">Normal</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>DESCRIPTION</label>
                <textarea value={editTaskDesc} onChange={(e) => setEditTaskDesc(e.target.value)} style={{ ...inputStyle, height: '90px', resize: 'vertical' }} />
              </div>

              <button type="submit" style={primaryBtnStyle}>Save Changes</button>
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