import React from 'react';

export const UserGuide: React.FC = () => {
  return (
    <div className="max-w-4xl mx-auto p-6 bg-white rounded-lg shadow-md my-8">
      <h1 className="text-3xl font-bold text-gray-900 mb-4">TaskFlow OS User Guide</h1>
      <p className="text-gray-600 mb-6">
        Welcome to TaskFlow OS! This guide will walk you through how to set up, navigate, and make the most of your multi-tenant workspace.
      </p>

      {/* Section 1: Getting Started */}
      <section className="mb-8">
        <h2 className="text-xl font-semibold text-gray-800 mb-3">1. Getting Started & Authentication</h2>
        <ul className="list-disc pl-5 space-y-2 text-gray-700">
          <li><strong>Google-Only Access:</strong> Registration and login are strictly restricted to verified Google (@gmail.com) accounts.</li>
          <li><strong>Company Registration:</strong> The first user to register becomes the <strong>Company Admin</strong>, establishing a secure and isolated tenant workspace.</li>
          <li><strong>Employee Joining:</strong> Team members joining via the portal must also authenticate using their `@gmail.com` accounts to be tied directly to your company's secure boundary.</li>
        </ul>
      </section>

      {/* Section 2: Roles and Permissions */}
      <section className="mb-8">
        <h2 className="text-xl font-semibold text-gray-800 mb-3">2. Roles & Strict Security Boundaries</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 bg-gray-50 rounded border border-gray-200">
            <h3 className="font-bold text-gray-900 mb-1">Company Admin</h3>
            <p className="text-sm text-gray-600">
              Has full control over the company workspace. Can create projects, establish groups, assign tasks, and monitor company-wide activity.
            </p>
          </div>
          <div className="p-4 bg-gray-50 rounded border border-gray-200">
            <h3 className="font-bold text-gray-900 mb-1">Regular User / Employee</h3>
            <p className="text-sm text-gray-600">
              Confined strictly to their company and assigned scope. Can view assigned tasks, update task statuses, and add comments. Cannot create or delete projects/groups.
            </p>
          </div>
        </div>
      </section>

      {/* Section 3: Step-by-Step Workflow */}
      <section className="mb-8">
        <h2 className="text-xl font-semibold text-gray-800 mb-3">3. Step-by-Step Workflow</h2>
        <ol className="list-decimal pl-5 space-y-3 text-gray-700">
          <li>
            <strong>Step 1: Log In</strong><br />
            Sign in securely using your Google-registered credential. Admins will receive automated security alerts on login.
          </li>
          <li>
            <strong>Step 2: Create Groups & Projects (Admins)</strong><br />
            Navigate to the dashboard to set up functional groups and initiate new projects. This instantly broadcasts real-time updates via WebSockets to all active company members.
          </li>
          <li>
            <strong>Step 3: Assign and Manage Tasks</strong><br />
            Assign tasks to team members. Assigned users will receive persistent database notifications and live alerts.
          </li>
          <li>
            <strong>Step 4: Track Progress & Update Status</strong><br />
            Team members update their task progress (e.g., changing status to <em>In Progress</em> or <em>Completed</em>) and collaborate directly via task comments.
          </li>
        </ol>
      </section>

     {/* Section 4: Real-Time Notifications */}
      <section className="mb-8">
        <h2 className="text-xl font-semibold text-gray-800 mb-3">4. Real-Time Notifications & Alerts</h2>
        <p className="text-gray-700">
          TaskFlow OS utilizes a three-layer notification architecture:
        </p>
        <ul className="list-disc pl-5 mt-2 space-y-1 text-gray-700">
          <li><strong>In-App Logs:</strong> Persistent database history tracking tasks, projects, and group events.</li>
          <li><strong>Live WebSockets:</strong> Instant banner alerts pushed directly to your browser as actions happen across your company.</li>
          <li><strong>Admin Security Emails:</strong> Automated SMTP email alerts dispatched for critical administrative security events.</li>
        </ul>
      </section>

      {/* Section 5: Project AI (Ask AI) */}
      <section>
        <h2 className="text-xl font-semibold text-gray-800 mb-3">5. Project AI (Ask AI)</h2>
        <p className="text-gray-700 mb-3">
          Inside a visible project, both <strong>Company Admins</strong> and <strong>Regular Users / Employees</strong> can use the <strong>Ask AI</strong> button and comment/question box anytime to ask Groq about that project. While only admins can create/delete projects and groups or add members, Project AI is available to any member with access to the project and uses the project&apos;s details (ID, name, description) along with up to 50 project tasks (ID, title, status, priority, description).
        </p>
        <ul className="list-disc pl-5 space-y-2 text-gray-700">
          <li>
            <strong>Step-by-Step Breakdowns &amp; Execution Order:</strong> Ask for a step-by-step breakdown of the project&apos;s tasks, which order to tackle them based on status and priority, or a breakdown of a specific task (such as <code>[#12]</code>) into concrete steps.
          </li>
          <li>
            <strong>Status Checks &amp; Progress Reviews:</strong> Ask about the current status of the project and its tasks, which tasks are still in progress or not started, or which high-priority tasks need attention right now.
          </li>
          <li>
            <strong>Explanations, Notes &amp; Comments:</strong> Ask what the project aims to achieve from its description and tasks, paste a progress note or comment to see how it fits with remaining tasks, or ask which tasks have unclear or missing descriptions.
          </li>
          <li>
            <strong>What Project AI Cannot Answer:</strong> It does not answer questions about other projects, company-wide member lists, admin/permission rules, or external live information outside the project and task data provided.
          </li>
        </ul>
      </section>
    </div>
  );
};
export default UserGuide;