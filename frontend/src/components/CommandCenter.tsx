export default function CommandCenter({ groups, projects, tasks, users }: any) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
        <div style={cardStyle}>
          <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 700 }}>DEPARTMENT GROUPS</div>
          <div style={{ fontSize: '26px', fontWeight: 800, color: '#38bdf8', marginTop: '6px' }}>{groups.length}</div>
        </div>
        <div style={cardStyle}>
          <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 700 }}>PROJECTS</div>
          <div style={{ fontSize: '26px', fontWeight: 800, color: '#818cf8', marginTop: '6px' }}>{projects.length}</div>
        </div>
        <div style={cardStyle}>
          <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 700 }}>DISPATCHED TASKS</div>
          <div style={{ fontSize: '26px', fontWeight: 800, color: '#a855f7', marginTop: '6px' }}>{tasks.length}</div>
        </div>
        <div style={cardStyle}>
          <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 700 }}>TEAM PERSONNEL</div>
          <div style={{ fontSize: '26px', fontWeight: 800, color: '#22c55e', marginTop: '6px' }}>{users.length}</div>
        </div>
      </div>
    </div>
  )
}
const cardStyle = { background: '#0c1322', border: '1px solid #1e293b', borderRadius: '16px', padding: '22px', display: 'flex', flexDirection: 'column' as const }