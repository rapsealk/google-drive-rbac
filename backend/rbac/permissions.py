"""Permission codenames and the code-defined role registry.

Roles are structure, not data: each role is a set of permission codenames,
with a hierarchy (admin implies editor implies viewer). The database stores
only *assignments* (see rbac.models).
"""

# --- Permission codenames ---
CONTENT_READ = "content:read"
CONTENT_WRITE = "content:write"
CONTENT_DELETE = "content:delete"
SHARE_GRANT = "share:grant"
WORKSPACE_MANAGE = "workspace:manage"
MEMBER_MANAGE = "member:manage"
AUDIT_READ = "audit:read"

ALL_PERMISSIONS = (
    CONTENT_READ,
    CONTENT_WRITE,
    CONTENT_DELETE,
    SHARE_GRANT,
    WORKSPACE_MANAGE,
    MEMBER_MANAGE,
    AUDIT_READ,
)

# --- Role names ---
# ROLE_USER / ROLE_ADMIN live on CompanyMembership (company scope).
# ROLE_VIEWER / ROLE_EDITOR are grantable on any node (rbac.RoleGrant).
ROLE_USER = "user"
ROLE_VIEWER = "viewer"
ROLE_EDITOR = "editor"
ROLE_ADMIN = "admin"

# Role hierarchy: each role implies every permission of the roles under it.
_ROLE_HIERARCHY = {
    ROLE_ADMIN: [ROLE_EDITOR],
    ROLE_EDITOR: [ROLE_VIEWER],
    ROLE_VIEWER: [],
    ROLE_USER: [],
}

# Direct permissions per role (before hierarchy expansion).
_ROLE_DIRECT = {
    ROLE_USER: set(),
    ROLE_VIEWER: {CONTENT_READ},
    ROLE_EDITOR: {CONTENT_READ, CONTENT_WRITE, CONTENT_DELETE, SHARE_GRANT},
    ROLE_ADMIN: {WORKSPACE_MANAGE, MEMBER_MANAGE, AUDIT_READ},
}


def role_permissions(role: str) -> frozenset:
    """Resolve a role to its full permission set, expanding the hierarchy."""
    if role not in _ROLE_DIRECT:
        raise ValueError(f"unknown role: {role!r}")
    perms = set(_ROLE_DIRECT[role])
    for parent in _ROLE_HIERARCHY[role]:
        perms |= role_permissions(parent)
    return frozenset(perms)


def is_valid_grant_role(role: str) -> bool:
    """Only node-scoped roles are grantable on resources."""
    return role in (ROLE_VIEWER, ROLE_EDITOR)
