"""API-level permission boundary tests.

Proves the boundaries over HTTP: a Company-A user cannot read Company-B's
file even with a forged URL, a plain `user` cannot hit admin endpoints,
presigned download requires the check, and the upload flow works.
"""

import pytest

from accounts import services as accounts_services
from accounts.models import InviteCode
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from files.models import StoredFile
from tenants.models import Workspace

User = get_user_model()


@pytest.fixture(autouse=True)
def no_minio(monkeypatch):
    monkeypatch.setattr("files.storage.delete_object", lambda key: None)


@pytest.fixture
def company_a(db):
    user, company, _ = accounts_services.signup_create_company("alice", "a@x.com", "password123", "Acme")
    return company


@pytest.fixture
def company_b(db):
    user, company, _ = accounts_services.signup_create_company("bob", "b@x.com", "password123", "Beta")
    return company


def client_for(username):
    c = APIClient()
    c.force_authenticate(user=User.objects.get(username=username))
    return c


@pytest.fixture
def ws(company_a):
    return Workspace.objects.create(company=company_a, name="team", default_role="viewer")


@pytest.fixture
def file_a(company_a, ws, no_minio):
    alice = User.objects.get(username="alice")
    StoredFile.objects.create(workspace=ws, name="secret.pdf", storage_key="uploads/abc", size=1)
    return StoredFile.objects.get(name="secret.pdf")


# --- Tenant isolation over HTTP ---


def test_cross_company_file_read_blocked(company_a, company_b, ws, file_a):
    c = client_for("bob")
    r = c.get(f"/api/files/{file_a.pk}")
    assert r.status_code == 403


def test_cross_company_workspace_contents_blocked(company_a, company_b, ws, file_a):
    c = client_for("bob")
    assert c.get(f"/api/workspaces/{ws.pk}/contents").status_code == 403
    assert c.get(f"/api/folders/nonexistent", format="json").status_code in (403, 404)


def test_workspace_list_excludes_other_company(company_a, company_b, ws):
    c = client_for("bob")
    r = c.get("/api/workspaces")
    assert r.status_code == 200
    assert all(w["id"] != ws.pk for w in r.json())


def test_workspace_list_shows_shared_workspace(company_a, ws):
    c = client_for("alice")
    r = c.get("/api/workspaces")
    assert [w["id"] for w in r.json()] == [ws.pk]


# --- Role boundaries over HTTP ---


@pytest.fixture
def member_user(company_a, alice_is_admin):
    alice = User.objects.get(username="alice")
    accounts_services.create_invite(alice)
    code = InviteCode.objects.first().code
    carol, _, _ = accounts_services.signup_join_company("carol", "c@x.com", "password123", code)
    return carol


@pytest.fixture
def alice_is_admin(company_a):
    return True


def test_plain_user_cannot_create_workspace(company_a, ws, member_user):
    c = client_for("carol")
    assert c.post("/api/workspaces", {"name": "sneaky"}, format="json").status_code == 403


def test_plain_user_cannot_hit_members(company_a, ws, member_user):
    c = client_for("carol")
    assert c.get("/api/members").status_code == 403


def test_plain_user_cannot_hit_audit(company_a, ws, member_user):
    c = client_for("carol")
    assert c.get("/api/audit").status_code == 403


def test_plain_user_cannot_grant(company_a, ws, member_user, file_a):
    c = client_for("carol")
    r = c.post("/api/grants", {"kind": "file", "node_id": file_a.pk, "username": "alice", "role": "editor"},
               format="json")
    assert r.status_code == 403


def test_editor_can_grant(company_a, ws, member_user, file_a):
    alice = User.objects.get(username="alice")
    from rbac.services import grant_role

    grant_role(alice, member_user, "editor", file_a)
    c = client_for("carol")
    r = c.post("/api/grants", {"kind": "file", "node_id": file_a.pk, "username": "alice", "role": "viewer"},
               format="json")
    assert r.status_code == 201


def test_admin_can_manage_members(company_a, member_user):
    c = client_for("alice")
    assert c.get("/api/members").status_code == 200
    assert len(c.get("/api/members").json()) == 2


def test_admin_cannot_remove_self(company_a):
    alice = User.objects.get(username="alice")
    c = client_for("alice")
    assert c.delete(f"/api/members/{alice.pk}").status_code == 400


def test_cross_company_grant_rejected(company_a, company_b, ws, file_a):
    c = client_for("alice")
    r = c.post("/api/grants", {"kind": "file", "node_id": file_a.pk, "username": "bob", "role": "viewer"},
               format="json")
    assert r.status_code == 400


# --- Upload / download flow ---


def test_presign_requires_write(company_a, ws, member_user):
    c = client_for("carol")  # ws default_role=viewer -> read only
    r = c.post("/api/files/presign", {
        "workspace_id": ws.pk, "name": "x.txt", "size": 10}, format="json")
    assert r.status_code == 403


def test_upload_flow_presign_finalize_download(company_a, ws, no_minio, monkeypatch):
    from files.storage import presign_put, presign_get

    alice = User.objects.get(username="alice")
    c = client_for("alice")
    monkeypatch.setattr("api.views.presign_put", lambda key, ct="": f"http://minio/put/{key}")
    monkeypatch.setattr("api.views.presign_get", lambda key: f"http://minio/get/{key}")

    r = c.post("/api/files/presign", {
        "workspace_id": ws.pk, "name": "doc.txt", "size": 10, "content_type": "text/plain"}, format="json")
    assert r.status_code == 201
    key = r.json()["key"]
    assert r.json()["upload_url"] == f"http://minio/put/{key}"

    r = c.post("/api/files/finalize", {
        "workspace_id": ws.pk, "name": "doc.txt", "key": key, "size": 10,
        "content_type": "text/plain"}, format="json")
    assert r.status_code == 201
    file_id = r.json()["id"]

    r = c.get(f"/api/files/{file_id}")
    assert r.status_code == 200
    assert r.json()["download_url"] == f"http://minio/get/{key}"


def test_finalize_rejects_bad_key(company_a, ws, no_minio):
    c = client_for("alice")
    r = c.post("/api/files/finalize", {
        "workspace_id": ws.pk, "name": "doc.txt", "key": "evil/path", "size": 10}, format="json")
    assert r.status_code == 400


def test_presign_rejects_oversize(company_a, ws):
    c = client_for("alice")
    r = c.post("/api/files/presign", {
        "workspace_id": ws.pk, "name": "big.bin", "size": 26 * 1024 * 1024}, format="json")
    assert r.status_code == 400


# --- Audit ---


def test_audit_lists_entries_for_admin(company_a, ws, file_a):
    alice = User.objects.get(username="alice")
    from files.services import delete_file

    delete_file(alice, file_a)
    c = client_for("alice")
    r = c.get("/api/audit")
    assert r.status_code == 200
    assert any(e["action"] == "file.delete" for e in r.json())
