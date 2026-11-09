"""The RBAC check engine.

Framework-agnostic: pure functions over the models, no HTTP, no DRF.

Check semantics (locked design):
- Walk up the tree file -> folder -> ... -> workspace -> company.
- Union of permissions, add-only (most permissive wins; no deny rules).
- Permission sources, in order of breadth:
  1. RoleGrants (viewer/editor) at any node on the ancestor chain.
  2. Workspace.default_role at the workspace level, for any company member.
  3. CompanyMembership.role == admin: everything on the company subtree.
"""

from functools import reduce
from operator import or_

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from rbac.models import AuditLog, RoleGrant
from rbac.permissions import (
    ALL_PERMISSIONS,
    ROLE_ADMIN,
    role_permissions,
)


def iter_ancestors(node):
    """Yield node, its parent, ... up to and including the Company."""
    while node is not None:
        yield node
        node = node.get_parent_node()


def company_of(node):
    return list(iter_ancestors(node))[-1]


def _workspace_of(chain):
    for obj in chain:
        if obj.__class__.__name__ == "Workspace":
            return obj
    return None


def _node_q(chain):
    """Q object matching any node in the chain."""
    parts = []
    for obj in chain:
        ct = ContentType.objects.get_for_model(type(obj))
        parts.append(Q(content_type=ct, object_id=obj.pk))
    return reduce(or_, parts)


def effective_permissions(user, node) -> frozenset:
    """All permissions `user` holds on `node`, unioned over the ancestor chain."""
    from accounts.models import CompanyMembership

    chain = list(iter_ancestors(node))
    company = chain[-1]

    membership = CompanyMembership.objects.filter(user=user, company=company).first()
    if membership is None:
        # Not a member of this tenant: no access, ever. Cross-tenant grants
        # cannot exist because RoleGrant creation validates same-company.
        return frozenset()

    # 1. Explicit node-scoped grants along the chain (one bulk query).
    grants = RoleGrant.objects.filter(user=user).filter(_node_q(chain))
    perms = set()
    for g in grants:
        perms |= role_permissions(g.role)

    # 2. Workspace default role, for any company member.
    workspace = _workspace_of(chain)
    if workspace is not None and workspace.default_role:
        perms |= role_permissions(workspace.default_role)

    # 3. Company admin: everything.
    if membership.role == ROLE_ADMIN:
        perms |= set(ALL_PERMISSIONS)

    return frozenset(perms)


def has_permission(user, perm: str, node) -> bool:
    return perm in effective_permissions(user, node)


# --- Grant/revoke (service layer: check, write, audit) ---


def grant_role(actor, user, role: str, node) -> RoleGrant:
    """Grant `user` `role` on `node`. Validates same-company; audits."""
    from accounts.models import CompanyMembership
    from rbac.permissions import is_valid_grant_role
    from django.core.exceptions import ValidationError

    if not is_valid_grant_role(role):
        raise ValidationError(f"role {role!r} is not grantable on resources")
    company = company_of(node)
    user_company = CompanyMembership.objects.filter(user=user).values_list("company_id", flat=True).first()
    if user_company != company.pk:
        raise ValidationError("cannot grant across companies")

    grant, _ = RoleGrant.objects.get_or_create(
        user=user,
        role=role,
        content_type=ContentType.objects.get_for_model(type(node)),
        object_id=node.pk,
        defaults={"granted_by": actor},
    )
    log_action(
        actor=actor, company=company, action=AuditLog.ACTION_GRANT_CREATE,
        target=node, user_id=user.pk, role=role,
    )
    return grant


def revoke_grant(actor, grant: RoleGrant):
    node = grant.target
    company = company_of(node)
    grant.delete()
    log_action(
        actor=actor, company=company, action=AuditLog.ACTION_GRANT_REVOKE,
        target=node, user_id=grant.user_id, role=grant.role,
    )


def log_action(actor, company, action, target=None, **metadata):
    """Append to the audit trail. Never raises to the caller's transaction."""
    ct = ContentType.objects.get_for_model(type(target)) if target is not None else None
    AuditLog.objects.create(
        actor=actor,
        company=company,
        action=action,
        content_type=ct,
        object_id=target.pk if target is not None else None,
        metadata=metadata,
    )
