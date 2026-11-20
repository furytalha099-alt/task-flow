import { useState } from 'react'

export default function GroupsView({ groups, projects, tasks, users, userRole, apiUrl, getCsrfToken, refreshData, setSuccessMsg }: any) {
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null)
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null)

  // Always derive live objects from props so refreshData() updates the UI immediately
  const selectedGroup = groups.find((g: any) => Number(g.id) === Number(selectedGroupId)) || null
  const selectedProject = projects.find((p: any) => Number(p.id) === Number(selectedProjectId)) || null

  // State for creating a new group
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [groupName, setGroupName] = useState('')
  const [groupDesc, setGroupDesc] = useState('')

  async function handleCreateGroup(e: React.FormEvent) {
    e.preventDefault()
    if (!groupName.trim()) return
    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/groups/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        body: JSON.stringify({ name: groupName.trim(), description: groupDesc.trim() || null })
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Failed to create group')
      }
      setSuccessMsg('Department group created successfully!')
      setGroupName('')
      setGroupDesc('')
      setShowCreateModal(false)
      await refreshData()
    } catch (err: any) {
      alert(err.message || 'Error creating group.')
    }
  }

  async function handleDeleteGroup(groupId: number) {
    if (!confirm('Are you sure you want to delete this group?')) return
    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/groups/${groupId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        }
      })
      if (!res.ok) throw new Error('Failed to delete group')
      setSuccessMsg('Department group deleted successfully.')
      setSelectedGroupId(null)
      setSelectedProjectId(null)
      await refreshData()
    } catch {
      alert('Error deleting group.')
    }
  }

  async function handleAddMember(groupId: number, userId: number) {
    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/groups/${groupId}/members/${userId}`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        }
      })
      if (!res.ok) throw new Error('Failed to add member')
      setSuccessMsg('Member added to group successfully!')
      await refreshData()
    } catch {
      alert('Failed to add member to group.')
    }
  }

  async function handleRemoveMember(groupId: number, userId: number) {
    try {
      const csrf = getCsrfToken()
      const res = await fetch(`${apiUrl}/groups/${groupId}/members/${userId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        }
      })
      if (!res.ok) throw new Error('Failed to remove member')
      setSuccessMsg('Member removed from group.')
      await refreshData()
    } catch {
      alert('Failed to remove member.')
    }
  }

  // Helper to resolve members strictly for a specific group
  function resolveGroupMembers(groupObj: any) {
    const rawMembers = groupObj?.users || groupObj?.members || []
    const seen = new Set<number>()
    const resolved: any[] = []
    for (const m of rawMembers) {
      const memberObj = typeof m === 'object' && m !== null
        ? m
        : users.find((u: any) => Number(u.id) === Number(m)) || { id: m, email: `User #${m}` }
      if (!seen.has(Number(memberObj.id))) {
        seen.add(Number(memberObj.id))
        resolved.push(memberObj)
      }
    }
    return resolved
  }

  // --- LEVEL 3: PROJECT INSPECTOR (Shows ALL Group Members with and without tasks) ---
  if (selectedProject && selectedGroup) {
    const groupMembers = resolveGroupMembers(selectedGroup)
    const projectTasks = tasks.filter((t: any) => Number(t.project_id) === Number(selectedProject.id))

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <button
          onClick={() => setSelectedProjectId(null)}
          style={{ background: '#1e293b', color: '#38bdf8', border: 'none', padding: '8px 16px', borderRadius: '8px', cursor: 'pointer', width: 'fit-content', fontWeight: 700, fontSize: '13px' }}
        >
          ← Back to {selectedGroup.name} Details
        </button>

        <div style={{ background: '#0c1322', border: '1px solid #1e293b', padding: '28px', borderRadius: '20px' }}>
          <span style={{ fontSize: '10px', background: '#131d31', color: '#818cf8', padding: '4px 10px', borderRadius: '6px', fontWeight: 700, textTransform: 'uppercase' }}>Department Project Audit</span>
          <h2 style={{ fontSize: '24px', fontWeight: 800, color: '#f8fafc', marginTop: '8px' }}>{selectedProject.name}</h2>
          <p style={{ fontSize: '14px', color: '#94a3b8', marginTop: '4px' }}>{selectedProject.description || 'No project description provided.'}</p>
        </div>

        <div>
          <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px', color: '#f8fafc' }}>
            Department Members & Task Breakdown ({groupMembers.length} Members)
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {groupMembers.length === 0 ? (
              <div style={{ background: '#0c1322', border: '1px solid #1e293b', padding: '24px', borderRadius: '14px', color: '#64748b', fontSize: '14px' }}>
                No members are currently assigned to {selectedGroup.name}. Go back to add personnel to this group.
              </div>
            ) : (
              groupMembers.map((member: any) => {
                const memberTasks = projectTasks.filter((t: any) => Number(t.assigned_to_id) === Number(member.id))

                return (
                  <div key={member.id} style={{ background: '#0c1322', border: '1px solid #1e293b', borderRadius: '16px', padding: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #1e293b', paddingBottom: '10px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{ width: '32px', height: '32px', background: '#131d31', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#38bdf8', fontWeight: 800, fontSize: '12px', border: '1px solid #334155' }}>
                          {member.email ? member.email[0].toUpperCase() : 'U'}
                        </div>
                        <div>
                          <span style={{ fontSize: '15px', fontWeight: 700, color: '#f8fafc', display: 'block' }}>{member.email || `User ID #${member.id}`}</span>
                          <span style={{ fontSize: '11px', color: '#64748b' }}>Department Personnel</span>
                        </div>
                      </div>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: memberTasks.length > 0 ? '#38bdf8' : '#64748b', background: '#131d31', padding: '4px 10px', borderRadius: '6px' }}>
                        {memberTasks.length} {memberTasks.length === 1 ? 'Task Assigned' : 'Tasks Assigned'}
                      </span>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {memberTasks.length === 0 ? (
                        <div style={{ fontSize: '13px', color: '#64748b', fontStyle: 'italic', padding: '4px 0' }}>
                          No tasks assigned to this user in this project yet.
                        </div>
                      ) : (
                        memberTasks.map((task: any) => (
                          <div key={task.id} style={{ background: '#131d31', borderRadius: '10px', padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', border: '1px solid #1e293b' }}>
                            <div>
                              <div style={{ fontSize: '14px', fontWeight: 700, color: '#f8fafc', marginBottom: '2px' }}>{task.title}</div>
                              <div style={{ fontSize: '12px', color: '#94a3b8' }}>Priority: <span style={{ textTransform: 'uppercase', color: '#cbd5e1', fontWeight: 600 }}>{task.priority || 'normal'}</span></div>
                            </div>
                            <span style={{ background: '#0c1322', color: task.status === 'done' ? '#22c55e' : '#38bdf8', border: '1px solid #334155', padding: '6px 12px', borderRadius: '8px', fontSize: '12px', fontWeight: 700 }}>
                              {task.status || 'todo'}
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      </div>
    )
  }

  // --- LEVEL 2: GROUP INSPECTOR (Shows Assigned Projects & Member Management) ---
  if (selectedGroup) {
    const groupProjects = projects.filter((p: any) => Number(p.group_id) === Number(selectedGroup.id))
    const groupMembers = resolveGroupMembers(selectedGroup)

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <button
            onClick={() => { setSelectedGroupId(null); setSelectedProjectId(null); }}
            style={{ background: '#1e293b', color: '#38bdf8', border: 'none', padding: '8px 16px', borderRadius: '8px', cursor: 'pointer', fontWeight: 700, fontSize: '13px' }}
          >
            ← Back to All Groups
          </button>
          {userRole === 'admin' && (
            <button
              onClick={() => handleDeleteGroup(selectedGroup.id)}
              style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', border: 'none', padding: '8px 16px', borderRadius: '8px', fontWeight: 700, fontSize: '13px', cursor: 'pointer' }}
            >
              Delete Group
            </button>
          )}
        </div>

        {/* Group Header */}
        <div style={{ background: '#0c1322', border: '1px solid #1e293b', padding: '28px', borderRadius: '20px' }}>
          <span style={{ fontSize: '10px', background: '#131d31', color: '#38bdf8', padding: '4px 10px', borderRadius: '6px', fontWeight: 700 }}>DEPARTMENT UNIT #{selectedGroup.id}</span>
          <h2 style={{ fontSize: '26px', fontWeight: 800, color: '#f8fafc', marginTop: '8px' }}>{selectedGroup.name}</h2>
          <p style={{ fontSize: '14px', color: '#94a3b8', marginTop: '4px' }}>{selectedGroup.description || 'No description provided for this department.'}</p>
        </div>

        {/* Section 1: Assigned Projects */}
        <div>
          <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px', color: '#f8fafc' }}>Assigned Projects ({groupProjects.length})</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px' }}>
            {groupProjects.length === 0 ? (
              <div style={{ background: '#0c1322', border: '1px solid #1e293b', padding: '24px', borderRadius: '14px', color: '#64748b', fontSize: '14px', gridColumn: '1 / -1' }}>
                No projects assigned to this group yet. Go to the Projects tab to create a project and assign it here!
              </div>
            ) : (
              groupProjects.map((proj: any) => (
                <div
                  key={proj.id}
                  onClick={() => setSelectedProjectId(proj.id)}
                  style={{ background: '#0c1322', border: '1px solid #1e293b', borderRadius: '16px', padding: '22px', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: '10px', transition: 'border-color 0.2s' }}
                >
                  <div style={{ fontSize: '17px', fontWeight: 700, color: '#f8fafc' }}>{proj.name}</div>
                  <div style={{ fontSize: '13px', color: '#94a3b8', flex: 1 }}>{proj.description || 'No description.'}</div>
                  <div style={{ fontSize: '13px', color: '#38bdf8', fontWeight: 700, marginTop: '8px', borderTop: '1px solid #1e293b', paddingTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>Inspect Project Tasks & Members</span>
                    <span>→</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Section 2: Member Management */}
        <div style={{ background: '#0c1322', border: '1px solid #1e293b', borderRadius: '20px', padding: '28px' }}>
          <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px', color: '#f8fafc' }}>Department Personnel & Member Allocation</h3>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
            {/* Current Members */}
            <div>
              <h4 style={{ fontSize: '13px', fontWeight: 700, color: '#64748b', marginBottom: '12px', textTransform: 'uppercase' }}>Current Group Members ({groupMembers.length})</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '250px', overflowY: 'auto' }}>
                {groupMembers.length === 0 ? (
                  <div style={{ fontSize: '13px', color: '#64748b', padding: '12px' }}>No members in this group.</div>
                ) : (
                  groupMembers.map((m: any) => (
                    <div key={m.id} style={{ background: '#131d31', padding: '10px 14px', borderRadius: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', border: '1px solid #1e293b' }}>
                      <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>{m.email || m.name || `User #${m.id}`}</span>
                      {userRole === 'admin' && (
                        <button
                          onClick={() => handleRemoveMember(selectedGroup.id, m.id)}
                          style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#f87171', border: 'none', padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 700, cursor: 'pointer' }}
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Add Available Company Members */}
            <div>
              <h4 style={{ fontSize: '13px', fontWeight: 700, color: '#64748b', marginBottom: '12px', textTransform: 'uppercase' }}>Add Company Personnel</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '250px', overflowY: 'auto' }}>
                {users.map((u: any) => {
                  const isAlreadyMember = groupMembers.some((gm: any) => Number(gm.id) === Number(u.id))
                  if (isAlreadyMember) return null
                  return (
                    <div key={u.id} style={{ background: '#131d31', padding: '10px 14px', borderRadius: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', border: '1px solid #1e293b' }}>
                      <span style={{ fontSize: '13px', fontWeight: 600, color: '#cbd5e1' }}>{u.email}</span>
                      {userRole === 'admin' && (
                        <button
                          onClick={() => handleAddMember(selectedGroup.id, u.id)}
                          style={{ background: 'linear-gradient(135deg, #6366f1 0%, #3b82f6 100%)', color: 'white', border: 'none', padding: '4px 12px', borderRadius: '6px', fontSize: '11px', fontWeight: 700, cursor: 'pointer' }}
                        >
                          + Add to Group
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // --- LEVEL 1: VIEW ALL GROUPS GRID ---
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#f8fafc' }}>Company Department Groups</h2>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '2px' }}>Organize personnel into specialized functional units.</p>
        </div>
        {userRole === 'admin' && (
          <button
            onClick={() => setShowCreateModal(true)}
            style={{ background: 'linear-gradient(135deg, #6366f1 0%, #3b82f6 100%)', color: 'white', border: 'none', padding: '10px 18px', borderRadius: '10px', fontWeight: 700, fontSize: '13px', cursor: 'pointer', boxShadow: '0 4px 15px rgba(99, 102, 241, 0.4)' }}
          >
            + Create New Group
          </button>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
        {groups.map((g: any) => {
          const groupProjects = projects.filter((p: any) => Number(p.group_id) === Number(g.id))
          const members = resolveGroupMembers(g)
          return (
            <div
              key={g.id}
              onClick={() => setSelectedGroupId(g.id)}
              style={{ background: '#0c1322', border: '1px solid #1e293b', borderRadius: '20px', padding: '24px', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: '16px', boxShadow: '0 4px 20px rgba(0,0,0,0.3)', transition: 'transform 0.2s' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>{g.name}</h3>
                <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 700, background: '#131d31', padding: '4px 10px', borderRadius: '8px' }}>ID #{g.id}</span>
              </div>

              <p style={{ fontSize: '13px', color: '#94a3b8', lineHeight: '1.5' }}>{g.description || 'No description provided.'}</p>

              <div style={{ display: 'flex', gap: '14px', fontSize: '12px', color: '#64748b', borderTop: '1px solid #1e293b', paddingTop: '14px' }}>
                <span>📁 <strong>{groupProjects.length}</strong> Projects</span>
                <span>•</span>
                <span>👥 <strong>{members.length}</strong> Members</span>
              </div>

              <div style={{ background: '#131d31', padding: '12px 16px', borderRadius: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', border: '1px solid #1e293b' }}>
                <span style={{ fontSize: '13px', fontWeight: 700, color: '#38bdf8' }}>View Department & Projects</span>
                <span style={{ fontSize: '15px', color: '#38bdf8' }}>→</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Create Group Modal */}
      {showCreateModal && (
        <div style={modalOverlayStyle}>
          <div style={modalContentStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>Create Department Group</h2>
              <button onClick={() => setShowCreateModal(false)} style={{ background: 'transparent', border: 'none', color: '#94a3b8', fontSize: '18px', cursor: 'pointer' }}>✕</button>
            </div>
            <form onSubmit={handleCreateGroup} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>GROUP NAME</label>
                <input type="text" required value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder="e.g. Core Engineering & Robotics" style={inputStyle} />
              </div>
              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>DESCRIPTION</label>
                <textarea value={groupDesc} onChange={(e) => setGroupDesc(e.target.value)} placeholder="Group purpose..." style={{ ...inputStyle, height: '90px', resize: 'vertical' }} />
              </div>
              <button type="submit" style={primaryBtnStyle}>Save Group</button>
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