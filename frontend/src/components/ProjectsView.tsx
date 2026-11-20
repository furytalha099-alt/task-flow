import { useEffect, useState } from 'react'
import { ProjectAIAskCard } from './ProjectAIAskCard'

export default function ProjectsView({ projects, groups, tasks, userRole, currentUserId, apiUrl, getCsrfToken, refreshData, setSuccessMsg }: any) {
  const [selectedProject, setSelectedProject] = useState<any | null>(null)
  const [showCommentBtn, setShowCommentBtn] = useState(false)
  const [showCommentBox, setShowCommentBox] = useState(false)
  const [commentTaskId, setCommentTaskId] = useState<number | ''>('')
  const [taskComments, setTaskComments] = useState<any[]>([])
  const [commentText, setCommentText] = useState('')
  const [loadingComments, setLoadingComments] = useState(false)
  const [postingComment, setPostingComment] = useState(false)
  const [commentError, setCommentError] = useState<string | null>(null)
  
  // State for creating a new project
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [projectName, setProjectName] = useState('')
  const [projectDesc, setProjectDesc] = useState('')
  const [targetGroupId, setTargetGroupId] = useState<string>('')

  // State for editing an existing project
  const [showEditModal, setShowEditModal] = useState(false)
  const [editProjectName, setEditProjectName] = useState('')
  const [editProjectDesc, setEditProjectDesc] = useState('')
  const [editTargetGroupId, setEditTargetGroupId] = useState<string>('')

  async function loadTaskComments(taskId: number) {
    setLoadingComments(true)
    setCommentError(null)
    try {
      const res = await fetch(`${apiUrl}/tasks/${taskId}/comments/`, {
        credentials: 'include',
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Failed to load comments')
      setTaskComments(Array.isArray(data) ? data : [])
    } catch (err: any) {
      setCommentError(err.message || 'Failed to load comments')
      setTaskComments([])
    } finally {
      setLoadingComments(false)
    }
  }

  async function handlePostTaskComment(e: React.FormEvent) {
    e.preventDefault()
    if (!commentTaskId || !commentText.trim()) return

    setPostingComment(true)
    setCommentError(null)
    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/tasks/${commentTaskId}/comments/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        body: JSON.stringify({ content: commentText.trim() }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Failed to post comment')

      setCommentText('')
      await loadTaskComments(Number(commentTaskId))
    } catch (err: any) {
      setCommentError(err.message || 'Failed to post comment')
    } finally {
      setPostingComment(false)
    }
  }

  useEffect(() => {
    if (showCommentBox && commentTaskId) {
      loadTaskComments(Number(commentTaskId))
    }
  }, [showCommentBox, commentTaskId])

  async function handleCreateProject(e: React.FormEvent) {
    e.preventDefault()
    if (!projectName.trim()) return

    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/projects/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        body: JSON.stringify({
          name: projectName.trim(),
          description: projectDesc.trim() || null,
          group_id: targetGroupId ? Number(targetGroupId) : null
        })
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Failed to create project')
      }

      setSuccessMsg('Project created and assigned successfully!')
      setProjectName('')
      setProjectDesc('')
      setTargetGroupId('')
      setShowCreateModal(false)
      refreshData()
    } catch (err: any) {
      alert(err.message || 'Error creating project.')
    }
  }

  async function handleUpdateProject(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedProject || !editProjectName.trim()) return

    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/projects/${selectedProject.id}`, {
        method: 'PUT',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        body: JSON.stringify({
          name: editProjectName.trim(),
          description: editProjectDesc.trim() || null,
          group_id: editTargetGroupId ? Number(editTargetGroupId) : null
        })
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Failed to update project')
      }

      const updatedProj = await res.json()
      setSuccessMsg('Project updated successfully!')
      setSelectedProject(updatedProj)
      setShowEditModal(false)
      refreshData()
    } catch (err: any) {
      alert(err.message || 'Error updating project.')
    }
  }

  function openEditModal() {
    if (!selectedProject) return
    setEditProjectName(selectedProject.name)
    setEditProjectDesc(selectedProject.description || '')
    setEditTargetGroupId(selectedProject.group_id ? String(selectedProject.group_id) : '')
    setShowEditModal(true)
  }

  async function handleDeleteProject(projectId: number) {
    if (!confirm('Are you sure you want to delete this project? All associated tasks may be affected.')) return

    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/projects/${projectId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        }
      })

      if (!res.ok) throw new Error('Failed to delete project')

      setSuccessMsg('Project deleted successfully.')
      setSelectedProject(null)
      refreshData()
    } catch {
      alert('Error deleting project. Ensure you have admin privileges.')
    }
  }

  // --- PROJECT INSPECTOR (View Tasks inside a selected project) ---
  if (selectedProject) {
    const projectTasks = tasks.filter((t: any) => Number(t.project_id) === Number(selectedProject.id))
    const assignedGroup = groups.find((g: any) => g.id === selectedProject.group_id)

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <button 
            onClick={() => {
              setSelectedProject(null)
              setShowCommentBtn(false)
              setShowCommentBox(false)
            }} 
            style={{ background: '#1e293b', color: '#38bdf8', border: 'none', padding: '8px 16px', borderRadius: '8px', cursor: 'pointer', fontWeight: 700, fontSize: '13px' }}
          >
            ← Back to All Projects
          </button>
          {userRole === 'admin' && (
            <div style={{ display: 'flex', gap: '10px' }}>
              <button 
                onClick={openEditModal}
                style={{ background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: 'none', padding: '8px 16px', borderRadius: '8px', fontWeight: 700, fontSize: '13px', cursor: 'pointer' }}
              >
                Edit Project
              </button>
              <button 
                onClick={() => handleDeleteProject(selectedProject.id)}
                style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', border: 'none', padding: '8px 16px', borderRadius: '8px', fontWeight: 700, fontSize: '13px', cursor: 'pointer' }}
              >
                Delete Project
              </button>
            </div>
          )}
        </div>

        <div style={{ background: '#0c1322', border: '1px solid #1e293b', padding: '28px', borderRadius: '20px' }}>
          <div style={{ display: 'flex', gap: '10px', marginBottom: '8px' }}>
            <span style={{ fontSize: '10px', background: '#131d31', color: '#38bdf8', padding: '4px 10px', borderRadius: '6px', fontWeight: 700 }}>PROJECT ID #{selectedProject.id}</span>
            {assignedGroup && (
              <span style={{ fontSize: '10px', background: 'rgba(99, 102, 241, 0.15)', color: '#818cf8', padding: '4px 10px', borderRadius: '6px', fontWeight: 700 }}>Group: {assignedGroup.name}</span>
            )}
          </div>
          <h2 style={{ fontSize: '26px', fontWeight: 800, color: '#f8fafc' }}>{selectedProject.name}</h2>
          <p style={{ fontSize: '14px', color: '#94a3b8', marginTop: '6px' }}>{selectedProject.description || 'No description provided.'}</p>

          {showCommentBtn && (
            <div style={{ marginTop: '14px' }}>
              <button
                type="button"
                onClick={() => {
                  const nextOpen = !showCommentBox
                  setShowCommentBox(nextOpen)
                  if (nextOpen && !commentTaskId) {
                    const firstTask = tasks.find((t: any) => Number(t.project_id) === Number(selectedProject.id))
                    if (firstTask) setCommentTaskId(firstTask.id)
                  }
                }}
                style={{
                  background: '#131d31',
                  color: '#38bdf8',
                  border: '1px solid #334155',
                  padding: '8px 14px',
                  borderRadius: '8px',
                  fontSize: '13px',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                {showCommentBox ? 'Hide Comment Box' : 'Comment'}
              </button>
            </div>
          )}

          {showCommentBox && (
            <div style={{ marginTop: '14px', background: '#131d31', border: '1px solid #334155', borderRadius: '12px', padding: '16px' }}>
              {projectTasks.length === 0 ? (
                <p style={{ fontSize: '13px', color: '#94a3b8', margin: 0 }}>
                  No tasks in this project yet.
                </p>
              ) : (
                <>
                  <div style={{ marginBottom: '12px' }}>
                    <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#94a3b8', marginBottom: '6px' }}>
                      SELECT TASK TO ASK / COMMENT
                    </label>
                    <select
                      value={commentTaskId}
                      onChange={(e) => setCommentTaskId(e.target.value ? Number(e.target.value) : '')}
                      style={{ ...inputStyle, marginTop: 0, padding: '8px 12px', fontSize: '13px' }}
                    >
                      {projectTasks.map((t: any) => (
                        <option key={t.id} value={t.id}>
                          {t.title} (#{t.id})
                        </option>
                      ))}
                    </select>
                  </div>

                  {commentError && (
                    <p style={{ fontSize: '12px', color: '#f87171', marginBottom: '10px' }}>{commentError}</p>
                  )}

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '180px', overflowY: 'auto', marginBottom: '12px' }}>
                    {loadingComments ? (
                      <p style={{ fontSize: '12px', color: '#94a3b8' }}>Loading comments...</p>
                    ) : taskComments.length === 0 ? (
                      <p style={{ fontSize: '12px', color: '#64748b' }}>No comments yet. Ask anything below.</p>
                    ) : (
                      taskComments.map((c: any) => (
                        <div key={c.id} style={{ background: '#0c1322', border: '1px solid #1e293b', borderRadius: '8px', padding: '10px' }}>
                          <div style={{ fontSize: '11px', fontWeight: 700, color: '#38bdf8' }}>
                            {c.author_email || `User #${c.user_id}`}
                          </div>
                          <div style={{ fontSize: '13px', color: '#e2e8f0', marginTop: '4px' }}>{c.content}</div>
                        </div>
                      ))
                    )}
                  </div>

                  <form onSubmit={handlePostTaskComment} style={{ display: 'flex', gap: '8px' }}>
                    <input
                      type="text"
                      value={commentText}
                      onChange={(e) => setCommentText(e.target.value)}
                      placeholder="Ask a question or leave a comment..."
                      disabled={postingComment || !commentTaskId}
                      style={{ ...inputStyle, marginTop: 0, padding: '10px 12px', fontSize: '13px', flex: 1 }}
                    />
                    <button
                      type="submit"
                      disabled={postingComment || !commentText.trim() || !commentTaskId}
                      style={{ ...primaryBtnStyle, padding: '10px 16px', whiteSpace: 'nowrap' }}
                    >
                      {postingComment ? 'Posting...' : 'Post'}
                    </button>
                  </form>
                </>
              )}
            </div>
          )}
        </div>

        <div>
          <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px', color: '#f8fafc' }}>Project Tasks ({projectTasks.length})</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {projectTasks.length === 0 ? (
              <div style={{ background: '#0c1322', border: '1px solid #1e293b', padding: '24px', borderRadius: '14px', color: '#64748b', fontSize: '14px' }}>
                No tasks created for this project yet. Go to the Task Operations tab to assign tasks here.
              </div>
            ) : (
              projectTasks.map((task: any) => (
                <div key={task.id} style={{ background: '#0c1322', border: '1px solid #1e293b', borderRadius: '14px', padding: '18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: '15px', fontWeight: 700, color: '#f8fafc', marginBottom: '4px' }}>{task.title}</div>
                    <div style={{ fontSize: '12px', color: '#94a3b8' }}>Priority: <span style={{ textTransform: 'uppercase', color: '#cbd5e1', fontWeight: 600 }}>{task.priority || 'normal'}</span></div>
                  </div>
                  <span style={{ background: '#131d31', color: task.status === 'done' ? '#22c55e' : '#38bdf8', border: '1px solid #334155', padding: '6px 12px', borderRadius: '8px', fontSize: '12px', fontWeight: 700 }}>
                    {task.status || 'todo'}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Edit Project Modal */}
        {showEditModal && (
          <div style={modalOverlayStyle}>
            <div style={modalContentStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <h2 style={{ fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>Edit Project</h2>
                <button onClick={() => setShowEditModal(false)} style={{ background: 'transparent', border: 'none', color: '#94a3b8', fontSize: '18px', cursor: 'pointer' }}>✕</button>
              </div>
              <form onSubmit={handleUpdateProject} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>PROJECT NAME</label>
                  <input type="text" required value={editProjectName} onChange={(e) => setEditProjectName(e.target.value)} style={inputStyle} />
                </div>

                <div>
                  <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>ASSIGN TO DEPARTMENT GROUP</label>
                  <select value={editTargetGroupId} onChange={(e) => setEditTargetGroupId(e.target.value)} style={inputStyle}>
                    <option value="">-- None / Independent Project --</option>
                    {groups.map((g: any) => (
                      <option key={g.id} value={g.id}>{g.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>DESCRIPTION</label>
                  <textarea value={editProjectDesc} onChange={(e) => setEditProjectDesc(e.target.value)} style={{ ...inputStyle, height: '90px', resize: 'vertical' }} />
                </div>

                <button type="submit" style={primaryBtnStyle}>Save Changes</button>
              </form>
            </div>
          </div>
        )}
      </div>
    )
  }

  // --- VIEW ALL PROJECTS GRID ---
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#f8fafc' }}>Workspace Projects</h2>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '2px' }}>Manage high-level project initiatives across department units.</p>
        </div>
        {userRole === 'admin' && (
          <button 
            onClick={() => setShowCreateModal(true)}
            style={{ background: 'linear-gradient(135deg, #6366f1 0%, #3b82f6 100%)', color: 'white', border: 'none', padding: '10px 18px', borderRadius: '10px', fontWeight: 700, fontSize: '13px', cursor: 'pointer', boxShadow: '0 4px 15px rgba(99, 102, 241, 0.4)' }}
          >
            + Create New Project
          </button>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
        {projects.length === 0 ? (
          <div style={{ background: '#0c1322', border: '1px solid #1e293b', padding: '32px', borderRadius: '20px', color: '#64748b', fontSize: '14px', gridColumn: '1 / -1', textAlign: 'center' }}>
            No projects found in the database. Create your first project above!
          </div>
        ) : (
          projects.map((proj: any) => {
            const assignedGroup = groups.find((g: any) => g.id === proj.group_id)
            const projTasks = tasks.filter((t: any) => Number(t.project_id) === Number(proj.id))
            return (
              <div 
                key={proj.id} 
                onClick={() => {
                  const firstTask = tasks.find((t: any) => Number(t.project_id) === Number(proj.id))
                  setSelectedProject(proj)
                  setShowCommentBtn(true)
                  setShowCommentBox(false)
                  setCommentTaskId(firstTask?.id ?? '')
                  setTaskComments([])
                  setCommentError(null)
                }}
                style={{ background: '#0c1322', border: '1px solid #1e293b', borderRadius: '20px', padding: '24px', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: '16px', boxShadow: '0 4px 20px rgba(0,0,0,0.3)', transition: 'transform 0.2s' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>{proj.name}</h3>
                  <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 700, background: '#131d31', padding: '4px 10px', borderRadius: '8px' }}>ID #{proj.id}</span>
                </div>
                
                <p style={{ fontSize: '13px', color: '#94a3b8', lineHeight: '1.5' }}>{proj.description || 'No description provided.'}</p>
                
                <div style={{ display: 'flex', gap: '14px', fontSize: '12px', color: '#64748b', borderTop: '1px solid #1e293b', paddingTop: '14px' }}>
                  <span>📁 <strong>{projTasks.length}</strong> Tasks</span>
                  <span>•</span>
                  <span>🏢 <strong style={{ color: '#818cf8' }}>{assignedGroup?.name || 'Unassigned Unit'}</strong></span>
                </div>

                <div style={{ background: '#131d31', padding: '12px 16px', borderRadius: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', border: '1px solid #1e293b' }}>
                  <span style={{ fontSize: '13px', fontWeight: 700, color: '#38bdf8' }}>Inspect Project & Tasks</span>
                  <span style={{ fontSize: '15px', color: '#38bdf8' }}>→</span>
                </div>

                <div onClick={(e) => e.stopPropagation()} style={{ width: '100%', boxSizing: 'border-box' }}>
                  <ProjectAIAskCard
                    project={proj}
                    currentUserId={currentUserId}
                    userRole={userRole}
                    apiBaseUrl={apiUrl}
                  />
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Create Project Modal */}
      {showCreateModal && (
        <div style={modalOverlayStyle}>
          <div style={modalContentStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>Create New Project</h2>
              <button onClick={() => setShowCreateModal(false)} style={{ background: 'transparent', border: 'none', color: '#94a3b8', fontSize: '18px', cursor: 'pointer' }}>✕</button>
            </div>
            <form onSubmit={handleCreateProject} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>PROJECT NAME</label>
                <input type="text" required value={projectName} onChange={(e) => setProjectName(e.target.value)} placeholder="e.g. Autonomous Navigation V2" style={inputStyle} />
              </div>

              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>ASSIGN TO DEPARTMENT GROUP</label>
                <select value={targetGroupId} onChange={(e) => setTargetGroupId(e.target.value)} style={inputStyle}>
                  <option value="">-- None / Independent Project --</option>
                  {groups.map((g: any) => (
                    <option key={g.id} value={g.id}>{g.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>DESCRIPTION</label>
                <textarea value={projectDesc} onChange={(e) => setProjectDesc(e.target.value)} placeholder="Project goals & specifications..." style={{ ...inputStyle, height: '90px', resize: 'vertical' }} />
              </div>

              <button type="submit" style={primaryBtnStyle}>Save & Initialize Project</button>
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