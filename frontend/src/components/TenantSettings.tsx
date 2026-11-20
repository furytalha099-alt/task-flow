export default function TenantSettings({ companyData }: any) {
  // Gracefully handle different possible property paths from FastAPI
  const company = companyData?.company || companyData || {}
  const name = company.name || company.company_name || 'TaskFlow Workspace'
  const subdomainRaw = company.subdomain || company.sub_domain
  const subdomain = subdomainRaw ? `${subdomainRaw}.taskflow.os` : 'wah-cantt-node'
  const adminEmail = company.admin_email || company.email || company.user_email || 'admin@taskflow.os'

  return (
    <div style={{ background: '#0c1322', border: '1px solid #1e293b', borderRadius: '20px', padding: '36px', maxWidth: '600px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
      <h3 style={{ fontSize: '20px', fontWeight: 800, color: '#f8fafc', marginBottom: '8px' }}>Tenant Workspace Settings</h3>
      <p style={{ fontSize: '13px', color: '#64748b', marginBottom: '28px' }}>Manage your organization's core metadata and access boundaries.</p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <div>
          <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', display: 'block', marginBottom: '6px', letterSpacing: '0.05em' }}>COMPANY NAME</label>
          <input 
            type="text" 
            readOnly 
            value={name} 
            style={inputStyle} 
          />
        </div>

        <div>
          <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', display: 'block', marginBottom: '6px', letterSpacing: '0.05em' }}>SUBDOMAIN</label>
          <input 
            type="text" 
            readOnly 
            value={subdomain} 
            style={{ ...inputStyle, color: '#38bdf8', fontFamily: 'monospace' }} 
          />
        </div>

        <div>
          <label style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', display: 'block', marginBottom: '6px', letterSpacing: '0.05em' }}>ADMIN CONTACT</label>
          <input 
            type="text" 
            readOnly 
            value={adminEmail} 
            style={inputStyle} 
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', padding: '16px 20px', borderRadius: '14px', marginTop: '8px' }}>
          <div>
            <div style={{ color: '#f8fafc', fontWeight: 700, fontSize: '14px' }}>RBAC Security Protocol</div>
            <div style={{ color: '#94a3b8', fontSize: '12px' }}>HTTP-only cookies & CSRF guard active</div>
          </div>
          <span style={{ background: '#22c55e', color: '#064e3b', padding: '4px 12px', borderRadius: '20px', fontSize: '11px', fontWeight: 800 }}>SECURE</span>
        </div>
      </div>
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
  outline: 'none',
  fontSize: '14px',
  boxSizing: 'border-box' as const,
  fontWeight: 600,
}