from tests.conftest import csrf_headers
import pytest
from app import main as app_main

def test_health_and_readiness(client):
    assert client.get("/health").status_code == 200
    assert client.get("/health/ready").status_code == 200


def test_unauthenticated_requests_rejected(client):
    assert client.get("/projects/").status_code == 401


def test_company_registration_login_and_project_creation(client):
    signup_res = client.post(
        "/companies/",
        json={
            "name": "Northstar Labs",
            "subdomain": "northstar-labs",
            "admin_email": "northstar.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert signup_res.status_code == 201, signup_res.text

    login_res = client.post(
        "/companies/login",
        json={
            "admin_email": "northstar.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert login_res.status_code == 200, login_res.text

    project_res = client.post(
        "/projects/",
        json={
            "name": "Core API",
            "description": "Backend service workstream",
            "group_id": None,
        },
        headers=csrf_headers(client),
    )
    assert project_res.status_code == 201, project_res.text
    assert project_res.json()["name"] == "Core API"


def test_multi_tenant_project_isolation(client):
    client.post(
        "/companies/",
        json={
            "name": "Tenant One",
            "subdomain": "tenant-one",
            "admin_email": "tenant.one@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    client.post(
        "/companies/login",
        json={
            "admin_email": "tenant.one@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    created = client.post(
        "/projects/",
        json={"name": "Secret Project A", "description": None, "group_id": None},
        headers=csrf_headers(client),
    )
    assert created.status_code == 201
    project_a_id = created.json()["id"]

    client.post("/companies/logout", headers=csrf_headers(client))
    client.post(
        "/companies/",
        json={
            "name": "Tenant Two",
            "subdomain": "tenant-two",
            "admin_email": "tenant.two@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    client.post(
        "/companies/login",
        json={
            "admin_email": "tenant.two@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )

    leak_res = client.get(f"/projects/{project_a_id}")
    assert leak_res.status_code == 404

def test_company_admin_me_refresh_and_logout(client):
    signup = client.post(
        "/companies/",
        json={
            "name": "Batch2 Admin Co",
            "subdomain": "batch2-admin",
            "admin_email": "batch2.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert signup.status_code == 201, signup.text

    login = client.post(
        "/companies/login",
        json={
            "admin_email": "batch2.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert login.status_code == 200, login.text

    me_res = client.get("/companies/me")
    assert me_res.status_code == 200, me_res.text
    assert me_res.json()["subdomain"] == "batch2-admin"

    refresh_res = client.post("/auth/refresh", headers=csrf_headers(client))
    assert refresh_res.status_code == 200, refresh_res.text

    logout_res = client.post("/companies/logout", headers=csrf_headers(client))
    assert logout_res.status_code == 200, logout_res.text

    after_logout = client.get("/companies/me")
    assert after_logout.status_code == 401


def test_user_login_me_refresh_and_logout(client):
    signup = client.post(
        "/companies/",
        json={
            "name": "Batch2 Member Co",
            "subdomain": "batch2-member",
            "admin_email": "member.host@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert signup.status_code == 201, signup.text

    admin_login = client.post(
        "/companies/login",
        json={
            "admin_email": "member.host@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert admin_login.status_code == 200, admin_login.text

    create_user = client.post(
        "/users/",
        json={
            "email": "staff.one@gmail.com",
            "password": "StaffPassword123!",
            "role": "member",
        },
        headers=csrf_headers(client),
    )
    assert create_user.status_code == 201, create_user.text

    # Log out admin session first so cookies belong cleanly to the user login
    admin_logout = client.post("/companies/logout", headers=csrf_headers(client))
    assert admin_logout.status_code == 200

    user_login = client.post(
        "/users/login",
        json={
            "email": "staff.one@gmail.com",
            "password": "StaffPassword123!",
        },
    )
    assert user_login.status_code == 200, user_login.text

    user_me = client.get("/companies/me")
    assert user_me.status_code == 200, user_me.text
    assert user_me.json()["subdomain"] == "batch2-member"

    user_refresh = client.post("/auth/refresh", headers=csrf_headers(client))
    assert user_refresh.status_code == 200, user_refresh.text

    user_logout = client.post("/users/logout", headers=csrf_headers(client))
    assert user_logout.status_code == 200, user_logout.text

    assert client.get("/companies/me").status_code == 401    

def test_company_update_patch_and_user_crud(client):
    signup = client.post(
        "/companies/",
        json={
            "name": "Batch3 Co",
            "subdomain": "batch3-co",
            "admin_email": "batch3.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert signup.status_code == 201, signup.text
    company_id = signup.json()["id"]

    login = client.post(
        "/companies/login",
        json={
            "admin_email": "batch3.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert login.status_code == 200, login.text

    headers = csrf_headers(client)

    # PUT /companies/{company_id}
    put_res = client.put(
        f"/companies/{company_id}",
        json={"name": "Batch3 Updated Co", "subdomain": "batch3-updated"},
        headers=headers,
    )
    assert put_res.status_code == 200, put_res.text
    assert put_res.json()["name"] == "Batch3 Updated Co"
    assert put_res.json()["subdomain"] == "batch3-updated"

    # PATCH /companies/{company_id}
    patch_res = client.patch(
        f"/companies/{company_id}",
        json={"name": "Batch3 Patched Co"},
        headers=headers,
    )
    assert patch_res.status_code == 200, patch_res.text
    assert patch_res.json()["name"] == "Batch3 Patched Co"

    # POST /users/
    create_user = client.post(
        "/users/",
        json={
            "email": "batch3.member@gmail.com",
            "password": "MemberPassword123!",
            "role": "member",
        },
        headers=headers,
    )
    assert create_user.status_code == 201, create_user.text
    user_id = create_user.json()["id"]

    # GET /users/
    list_users = client.get("/users/")
    assert list_users.status_code == 200, list_users.text
    assert any(u["id"] == user_id and u["email"] == "batch3.member@gmail.com" for u in list_users.json())

    # DELETE /users/{user_id}
    delete_user = client.delete(f"/users/{user_id}", headers=headers)
    assert delete_user.status_code == 204, delete_user.text

    list_after_delete = client.get("/users/")
    assert list_after_delete.status_code == 200
    assert all(u["id"] != user_id for u in list_after_delete.json())    

@pytest.fixture(autouse=True)
def _reset_rate_limits():
    with app_main._rate_lock:
        app_main._memory_buckets.clear()
    yield
    with app_main._rate_lock:
        app_main._memory_buckets.clear()    

def test_projects_list_update_delete_and_cross_tenant_protection(client):
    signup_a = client.post(
        "/companies/",
        json={
            "name": "Batch4 Alpha",
            "subdomain": "batch4-alpha",
            "admin_email": "batch4.alpha@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert signup_a.status_code == 201, signup_a.text

    login_a = client.post(
        "/companies/login",
        json={
            "admin_email": "batch4.alpha@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert login_a.status_code == 200, login_a.text
    headers_a = csrf_headers(client)

    created = client.post(
        "/projects/",
        json={
            "name": "Alpha Core API",
            "description": "Initial project description",
            "group_id": None,
        },
        headers=headers_a,
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    # GET /projects/
    listed = client.get("/projects/")
    assert listed.status_code == 200, listed.text
    assert any(p["id"] == project_id and p["name"] == "Alpha Core API" for p in listed.json())

    # PUT /projects/{project_id}
    updated = client.put(
        f"/projects/{project_id}",
        json={
            "name": "Alpha Core API v2",
            "description": "Updated description",
            "group_id": None,
        },
        headers=headers_a,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Alpha Core API v2"
    assert updated.json()["description"] == "Updated description"

    logout_a = client.post("/companies/logout", headers=headers_a)
    assert logout_a.status_code == 200

    # Second tenant cannot update or delete Alpha's project
    signup_b = client.post(
        "/companies/",
        json={
            "name": "Batch4 Beta",
            "subdomain": "batch4-beta",
            "admin_email": "batch4.beta@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert signup_b.status_code == 201, signup_b.text

    login_b = client.post(
        "/companies/login",
        json={
            "admin_email": "batch4.beta@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert login_b.status_code == 200, login_b.text
    headers_b = csrf_headers(client)

    assert client.put(
        f"/projects/{project_id}",
        json={"name": "Hijacked Name", "description": None, "group_id": None},
        headers=headers_b,
    ).status_code == 404
    assert client.delete(f"/projects/{project_id}", headers=headers_b).status_code == 404

    logout_b = client.post("/companies/logout", headers=headers_b)
    assert logout_b.status_code == 200

    # DELETE /projects/{project_id} as owner
    relogin_a = client.post(
        "/companies/login",
        json={
            "admin_email": "batch4.alpha@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert relogin_a.status_code == 200
    deleted = client.delete(f"/projects/{project_id}", headers=csrf_headers(client))
    assert deleted.status_code == 204, deleted.text

    after_delete = client.get(f"/projects/{project_id}")
    assert after_delete.status_code == 404        

def test_groups_and_member_management(client):
    signup = client.post(
        "/companies/",
        json={
            "name": "Batch5 Groups Co",
            "subdomain": "batch5-groups",
            "admin_email": "batch5.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert signup.status_code == 201, signup.text

    login = client.post(
        "/companies/login",
        json={
            "admin_email": "batch5.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert login.status_code == 200, login.text
    headers = csrf_headers(client)

    # Create a member user to add/remove from the group
    user_res = client.post(
        "/users/",
        json={
            "email": "group.member@gmail.com",
            "password": "GroupMemberPassword123!",
            "role": "member",
        },
        headers=headers,
    )
    assert user_res.status_code == 201, user_res.text
    user_id = user_res.json()["id"]

    # POST /groups/
    group_res = client.post(
        "/groups/",
        json={"name": "Platform Engineers", "description": "Backend and infra"},
        headers=headers,
    )
    assert group_res.status_code == 201, group_res.text
    group_id = group_res.json()["id"]

    # GET /groups/
    list_res = client.get("/groups/")
    assert list_res.status_code == 200, list_res.text
    assert any(g["id"] == group_id and g["name"] == "Platform Engineers" for g in list_res.json())

    # POST /groups/{group_id}/members/{user_id}
    add_member = client.post(f"/groups/{group_id}/members/{user_id}", headers=headers)
    assert add_member.status_code == 204, add_member.text

    # DELETE /groups/{group_id}/members/{user_id}
    remove_member = client.delete(f"/groups/{group_id}/members/{user_id}", headers=headers)
    assert remove_member.status_code == 204, remove_member.text

    # DELETE /groups/{group_id}
    delete_group = client.delete(f"/groups/{group_id}", headers=headers)
    assert delete_group.status_code == 204, delete_group.text

    after_delete = client.get("/groups/")
    assert after_delete.status_code == 200
    assert all(g["id"] != group_id for g in after_delete.json())    

def test_tasks_create_list_update_status_and_delete(client):
    signup = client.post(
        "/companies/",
        json={
            "name": "Batch6 Tasks Co",
            "subdomain": "batch6-tasks",
            "admin_email": "batch6.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert signup.status_code == 201, signup.text

    login = client.post(
        "/companies/login",
        json={
            "admin_email": "batch6.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert login.status_code == 200, login.text
    headers = csrf_headers(client)

    proj_res = client.post(
        "/projects/",
        json={"name": "TaskFlow Core", "description": "Task endpoints test", "group_id": None},
        headers=headers,
    )
    assert proj_res.status_code == 201, proj_res.text
    project_id = proj_res.json()["id"]

    # POST /tasks/
    create_res = client.post(
        "/tasks/",
        json={
            "title": "Build CI workflow",
            "description": "Add pytest and docker steps",
            "project_id": project_id,
            "status": "todo",
            "priority": "high",
        },
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    task_id = create_res.json()["id"]

    # GET /tasks/
    list_res = client.get("/tasks/")
    assert list_res.status_code == 200, list_res.text
    assert any(t["id"] == task_id and t["title"] == "Build CI workflow" for t in list_res.json())

    # PUT /tasks/{task_id}
    edit_res = client.put(
        f"/tasks/{task_id}",
        json={
            "title": "Build CI & CD workflow",
            "description": "Updated task details",
            "project_id": project_id,
            "status": "todo",
            "priority": "normal",
            "due_at": None,
            "assigned_to_id": None,
        },
        headers=headers,
    )
    assert edit_res.status_code == 200, edit_res.text
    assert edit_res.json()["title"] == "Build CI & CD workflow"

    # PATCH /tasks/{task_id}/status
    status_res = client.patch(
        f"/tasks/{task_id}/status",
        json={"status": "in_progress"},
        headers=headers,
    )
    assert status_res.status_code == 200, status_res.text
    assert status_res.json()["status"] == "in_progress"

    # DELETE /tasks/{task_id}
    delete_res = client.delete(f"/tasks/{task_id}", headers=headers)
    assert delete_res.status_code == 204, delete_res.text

    after_delete = client.get("/tasks/")
    assert after_delete.status_code == 200
    assert all(t["id"] != task_id for t in after_delete.json())    

def test_task_comments_and_notifications_workflow(client):
    signup = client.post(
        "/companies/",
        json={
            "name": "Batch7 Comms Co",
            "subdomain": "batch7-comms",
            "admin_email": "batch7.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert signup.status_code == 201, signup.text

    admin_login = client.post(
        "/companies/login",
        json={
            "admin_email": "batch7.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert admin_login.status_code == 200, admin_login.text
    admin_headers = csrf_headers(client)

    # Create a member user and assign a task to them
    user_res = client.post(
        "/users/",
        json={
            "email": "comment.user@gmail.com",
            "password": "CommentUserPassword123!",
            "role": "member",
        },
        headers=admin_headers,
    )
    assert user_res.status_code == 201, user_res.text
    user_id = user_res.json()["id"]

    proj_res = client.post(
        "/projects/",
        json={"name": "Comms Project", "description": "Comments & notifications", "group_id": None},
        headers=admin_headers,
    )
    assert proj_res.status_code == 201, proj_res.text
    project_id = proj_res.json()["id"]

    task_res = client.post(
        "/tasks/",
        json={
            "title": "Review PR security",
            "description": "Check cookie flags and CSRF",
            "project_id": project_id,
            "status": "todo",
            "priority": "high",
            "assigned_to_id": user_id,
        },
        headers=admin_headers,
    )
    assert task_res.status_code == 201, task_res.text
    task_id = task_res.json()["id"]

    # Switch to assigned user session to post a task comment
    assert client.post("/companies/logout", headers=admin_headers).status_code == 200

    user_login = client.post(
        "/users/login",
        json={
            "email": "comment.user@gmail.com",
            "password": "CommentUserPassword123!",
        },
    )
    assert user_login.status_code == 200, user_login.text
    user_headers = csrf_headers(client)

    # POST /tasks/{task_id}/comments/
    comment_create = client.post(
        f"/tasks/{task_id}/comments/",
        json={"content": "Checked CSRF validation and session cookies."},
        headers=user_headers,
    )
    assert comment_create.status_code == 201, comment_create.text
    assert comment_create.json()["content"] == "Checked CSRF validation and session cookies."

    # GET /tasks/{task_id}/comments/
    comments_list = client.get(f"/tasks/{task_id}/comments/")
    assert comments_list.status_code == 200, comments_list.text
    assert any(c["author_email"] == "comment.user@gmail.com" for c in comments_list.json())

    # GET /notifications/ & PATCH /notifications/{notification_id}/read
    notifs_res = client.get("/notifications/")
    assert notifs_res.status_code == 200, notifs_res.text
    notifs = notifs_res.json()
    assert len(notifs) >= 1

    notif_id = notifs[0]["id"]
    mark_read = client.patch(f"/notifications/{notif_id}/read", headers=user_headers)
    assert mark_read.status_code == 200, mark_read.text
    assert mark_read.json()["is_read"] is True    

def test_admin_audit_and_platform_admin_endpoints(client, monkeypatch):
    from app import main as app_main

    master_key = "test-platform-master-key-32-chars-minimum!!"
    monkeypatch.setattr(app_main, "PLATFORM_MASTER_KEY", master_key)

    signup = client.post(
        "/companies/",
        json={
            "name": "Batch8 Audit Co",
            "subdomain": "batch8-audit",
            "admin_email": "batch8.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert signup.status_code == 201, signup.text
    company_id = signup.json()["id"]

    login = client.post(
        "/companies/login",
        json={
            "admin_email": "batch8.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert login.status_code == 200, login.text

    # GET /admin/audit
    audit_res = client.get("/admin/audit")
    assert audit_res.status_code == 200, audit_res.text
    assert len(audit_res.json()) >= 1

    # Platform admin routes require valid X-Platform-Admin-Key
    bad_key_res = client.get("/admin/companies", headers={"X-Platform-Admin-Key": "wrong-key"})
    assert bad_key_res.status_code == 403

    admin_headers = {"X-Platform-Admin-Key": master_key}

    companies_res = client.get("/admin/companies", headers=admin_headers)
    assert companies_res.status_code == 200, companies_res.text
    assert any(c["id"] == company_id for c in companies_res.json())

    platform_audit_res = client.get("/platform/audit", headers=admin_headers)
    assert platform_audit_res.status_code == 200, platform_audit_res.text
    assert len(platform_audit_res.json()) >= 1

    del_company_res = client.delete(f"/admin/companies/{company_id}", headers=admin_headers)
    assert del_company_res.status_code == 204, del_company_res.text


def test_task_and_project_ai_endpoints(client, monkeypatch):
    from app import main as app_main

    def fake_ai_response(db, task, mode, question=None):
        return f"Mocked {mode} response for {task.title}", "mock-model-v1"

    monkeypatch.setattr(app_main, "generate_task_ai_response", fake_ai_response)

    signup = client.post(
        "/companies/",
        json={
            "name": "Batch8 AI Co",
            "subdomain": "batch8-ai",
            "admin_email": "batch8.ai@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert signup.status_code == 201, signup.text

    login = client.post(
        "/companies/login",
        json={
            "admin_email": "batch8.ai@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert login.status_code == 200, login.text
    headers = csrf_headers(client)

    proj_res = client.post(
        "/projects/",
        json={"name": "AI Engine Project", "description": "AI endpoint checks", "group_id": None},
        headers=headers,
    )
    assert proj_res.status_code == 201, proj_res.text
    project_id = proj_res.json()["id"]

    task_res = client.post(
        "/tasks/",
        json={
            "title": "Summarize sprint goals",
            "description": "Draft sprint summary",
            "project_id": project_id,
            "status": "todo",
            "priority": "normal",
        },
        headers=headers,
    )
    assert task_res.status_code == 201, task_res.text
    task_id = task_res.json()["id"]

    task_ai = client.post(
        f"/tasks/{task_id}/ai",
        json={"mode": "summarize", "question": None},
        headers=headers,
    )
    assert task_ai.status_code == 200, task_ai.text
    assert task_ai.json()["model"] == "mock-model-v1"

    proj_ai = client.post(
        f"/projects/{project_id}/ai",
        json={"mode": "ask", "question": "What are the active tasks?"},
        headers=headers,
    )
    assert proj_ai.status_code == 200, proj_ai.text
    assert proj_ai.json()["model"] == "mock-model-v1"


def test_google_auth_and_websocket_notifications(client, monkeypatch):
    from app import main as app_main

    signup = client.post(
        "/companies/",
        json={
            "name": "Batch8 Google WS Co",
            "subdomain": "batch8-gws",
            "admin_email": "google.admin@gmail.com",
            "admin_password": "StrongPassword123!",
        },
    )
    assert signup.status_code == 201, signup.text
    company_id = signup.json()["id"]

    def fake_verify_oauth2_token(token, request_obj, audience):
        return {"email": "google.admin@gmail.com", "email_verified": True}

    monkeypatch.setattr(app_main.id_token, "verify_oauth2_token", fake_verify_oauth2_token)

    google_res = client.post("/auth/google", json={"credential": "mock-google-id-token"})
    assert google_res.status_code == 200, google_res.text

    me_res = client.get("/companies/me")
    assert me_res.status_code == 200, me_res.text
    assert me_res.json()["id"] == company_id

    with client.websocket_connect("/ws/notifications") as ws:
        ws.send_text("ping")