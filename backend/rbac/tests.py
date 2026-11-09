"""Exhaustive tests for the RBAC check engine and permission boundaries.

The matrix (signed off):
  User (company)  = no permissions at company scope
  Viewer (node)   = content:read
  Editor (node)   = content:read, write, delete, share:grant
  Admin (company) = everything everywhere on the company subtree
Workspace.default_role applies at workspace level for any company member.
Check = walk up the tree, union, add-only.
"""

import pytest

from accounts import services as accounts_services
from accounts.models import CompanyMembership
from django.contrib.auth import get_user_model

from files.services import create_folder, finalize_upload
from rbac.models import RoleGrant
from rbac.permissions import (
    AUDIT_READ,
    CONTENT_DELETE,
    CONTENT_READ,
    CONTENT_WRITE,
    MEMBER_MANAGE,
    SHARE_GRANT,
    WORKSPACE_MANAGE,
)
from rbac.services import effective_permissions, grant_role, has_permission
from tenants.models import Company, Workspace

User = get_user_model()


@pytest.fixture(autouse=True)
def no_minio(monkeypatch):
    """Engine tests never touch object storage."""
    monkeypatch.setattr("files.storage.delete_object", lambda key: None)


@pytest.fixture
def company_a(db):
    user, company, _ = accounts_services.signup_create_company("alice", "a@x.com", "password123", "Acme")
    return company


@pytest.fixture
def company_b(db):
    user, company, _ = accounts_services.signup_create_company("bob", "b@x.com", "password123", "Beta")
    return company


@pytest.fixture
def alice(company_a):
    return User.objects.get(username="alice")


@pytest.fixture
def bob(company_b):
    return User.objects.get(username="bob")


@pytest.fixture
def ws(company_a):
    return Workspace.objects.create(company=company_a, name="team-ws", default_role="")


def make_tree(ws, folder_name="docs"):
    parent = create_folder(ws.company.memberships.first().user, ws, None, folder_name)
    child = create_folder(ws.company.memberships.first().user, ws, parent, "nested")
    f = finalize_upload(ws.company.memberships.first().user, ws, child, "report.pdf", "uploads/t1", 100, "application/pdf")
    return parent, child, f


# --- Role registry ---


@pytest.mark.django_db
def test_role_hierarchy_expansion():
    from rbac.permissions import role_permissions

    assert role_permissions("viewer") == frozenset({CONTENT_READ})
    assert role_permissions("editor") == frozenset({CONTENT_READ, CONTENT_WRITE, CONTENT_DELETE, SHARE_GRANT})
    admin = role_permissions("admin")
    for p in (CONTENT_READ, CONTENT_WRITE, CONTENT_DELETE, SHARE_GRANT, WORKSPACE_MANAGE, MEMBER_MANAGE, AUDIT_READ):
        assert p in admin
    assert role_permissions("user") == frozenset()


@pytest.mark.django_db
def test_unknown_role_raises():
    from rbac.permissions import role_permissions

    with pytest.raises(ValueError):
        role_permissions("superboss")


# --- The check engine ---


@pytest.mark.django_db
def test_company_admin_has_everything_alice(company_a, ws, alice):
    parent, child, f = make_tree(ws)
    for perm in (CONTENT_READ, CONTENT_WRITE, CONTENT_DELETE, SHARE_GRANT, WORKSPACE_MANAGE, MEMBER_MANAGE, AUDIT_READ):
        assert has_permission(alice, perm, f), f"admin should have {perm} on a deep file"


@pytest.mark.django_db
def test_plain_user_has_nothing_by_default(company_a, ws, alice):
    # A second user joins the company via invite (plain "user" role).
    accounts_services.create_invite(alice)
    from accounts.models import InviteCode

    code = InviteCode.objects.first().code
    carol, _, _ = accounts_services.signup_join_company("carol", "c@x.com", "password123", code)
    parent, child, f = make_tree(ws)
    assert effective_permissions(carol, f) == frozenset()


@pytest.mark.django_db
def test_workspace_default_role_gives_read_to_every_member(company_a, ws, alice):
    ws.default_role = "viewer"
    ws.save()
    accounts_services.create_invite(alice)
    from accounts.models import InviteCode

    code = InviteCode.objects.first().code
    carol, _, _ = accounts_services.signup_join_company("carol", "c@x.com", "password123", code)
    parent, child, f = make_tree(ws)
    assert has_permission(carol, CONTENT_READ, f)
    assert not has_permission(carol, CONTENT_WRITE, f)
    assert not has_permission(carol, CONTENT_DELETE, f)


@pytest.mark.django_db
def test_default_role_does_not_leak_to_other_companies(company_a, ws, bob):
    ws.default_role = "viewer"
    ws.save()
    parent, child, f = make_tree(ws)
    assert not has_permission(bob, CONTENT_READ, f)


@pytest.mark.django_db
def test_node_grant_on_folder_inherits_down(company_a, ws, alice):
    accounts_services.create_invite(alice)
    from accounts.models import InviteCode

    code = InviteCode.objects.first().code
    carol, _, _ = accounts_services.signup_join_company("carol", "c@x.com", "password123", code)
    parent, child, f = make_tree(ws)
    grant_role(alice, carol, "editor", parent)
    assert has_permission(carol, CONTENT_READ, f)
    assert has_permission(carol, CONTENT_WRITE, f)
    assert has_permission(carol, CONTENT_DELETE, f)
    assert has_permission(carol, SHARE_GRANT, f)
    # Editor on a folder does NOT manage workspaces or members.
    assert not has_permission(carol, WORKSPACE_MANAGE, f)
    assert not has_permission(carol, MEMBER_MANAGE, f)


@pytest.mark.django_db
def test_union_most_permissive_wins(company_a, ws, alice):
    """Add-only: viewer default on workspace + editor grant on file = editor perms."""
    ws.default_role = "viewer"
    ws.save()
    accounts_services.create_invite(alice)
    from accounts.models import InviteCode

    code = InviteCode.objects.first().code
    carol, _, _ = accounts_services.signup_join_company("carol", "c@x.com", "password123", code)
    parent, child, f = make_tree(ws)
    grant_role(alice, carol, "viewer", f)
    assert has_permission(carol, CONTENT_READ, f)
    assert not has_permission(carol, CONTENT_WRITE, f)
    grant_role(alice, carol, "editor", f)  # second grant, same node
    assert has_permission(carol, CONTENT_WRITE, f)


@pytest.mark.django_db
def test_cross_tenant_grant_impossible(company_a, ws, alice, bob):
    parent, child, f = make_tree(ws)
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        grant_role(alice, bob, "viewer", f)
    assert effective_permissions(bob, f) == frozenset()


@pytest.mark.django_db
def test_non_member_has_no_access_even_with_forged_grant(company_a, ws, bob):
    from files.models import StoredFile
    from django.contrib.contenttypes.models import ContentType

    parent, child, f = make_tree(ws)
    # Forge a grant row directly (bypassing service validation).
    RoleGrant.objects.create(
        user=bob, role="editor",
        content_type=ContentType.objects.get_for_model(StoredFile),
        object_id=f.pk,
    )
    assert effective_permissions(bob, f) == frozenset()


@pytest.mark.django_db
def test_grant_at_file_level_beats_nothing_at_company_level(company_a, ws, alice):
    accounts_services.create_invite(alice)
    from accounts.models import InviteCode

    code = InviteCode.objects.first().code
    carol, _, _ = accounts_services.signup_join_company("carol", "c@x.com", "password123", code)
    parent, child, f = make_tree(ws)
    grant_role(alice, carol, "viewer", f)
    assert has_permission(carol, CONTENT_READ, f)


@pytest.mark.django_db
def test_member_leaving_company_loses_everything(company_a, ws, alice):
    accounts_services.create_invite(alice)
    from accounts.models import InviteCode

    code = InviteCode.objects.first().code
    carol, _, _ = accounts_services.signup_join_company("carol", "c@x.com", "password123", code)
    parent, child, f = make_tree(ws)
    grant_role(alice, carol, "editor", f)
    ws.default_role = "viewer"
    ws.save()
    assert has_permission(carol, CONTENT_READ, f)
    CompanyMembership.objects.get(user=carol).delete()
    assert effective_permissions(carol, f) == frozenset()


@pytest.mark.django_db
def test_root_file_hangs_off_workspace(company_a, ws, alice):
    accounts_services.create_invite(alice)
    from accounts.models import InviteCode

    code = InviteCode.objects.first().code
    carol, _, _ = accounts_services.signup_join_company("carol", "c@x.com", "password123", code)
    f = finalize_upload(alice, ws, None, "top.pdf", "uploads/t2", 10, "")
    grant_role(alice, carol, "editor", ws)
    assert has_permission(carol, CONTENT_WRITE, f)
    assert has_permission(carol, CONTENT_DELETE, f)


@pytest.mark.django_db
def test_promoting_member_to_admin_grants_everything(company_a, ws, alice):
    accounts_services.create_invite(alice)
    from accounts.models import InviteCode

    code = InviteCode.objects.first().code
    carol, _, _ = accounts_services.signup_join_company("carol", "c@x.com", "password123", code)
    parent, child, f = make_tree(ws)
    accounts_services.change_member_role(alice, carol, "admin")
    assert has_permission(carol, MEMBER_MANAGE, f)
    assert has_permission(carol, AUDIT_READ, f)


# --- Audit trail ---


@pytest.mark.django_db
def test_grant_and_revoke_audited(company_a, ws, alice):
    from accounts.models import InviteCode

    accounts_services.create_invite(alice)
    code = InviteCode.objects.first().code
    carol, _, _ = accounts_services.signup_join_company("carol", "c@x.com", "password123", code)
    parent, child, f = make_tree(ws)
    grant = grant_role(alice, carol, "viewer", f)
    from rbac.services import revoke_grant
    from rbac.models import AuditLog

    revoke_grant(alice, grant)
    actions = list(AuditLog.objects.values_list("action", flat=True))
    assert "grant.create" in actions
    assert "grant.revoke" in actions


@pytest.mark.django_db
def test_file_delete_audited(company_a, ws, alice):
    from rbac.models import AuditLog

    parent, child, f = make_tree(ws)
    from files.services import delete_file

    delete_file(alice, f)
    entry = AuditLog.objects.filter(action="file.delete").first()
    assert entry is not None
    assert entry.metadata["file_name"] == "report.pdf"
