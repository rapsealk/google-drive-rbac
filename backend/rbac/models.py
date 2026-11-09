from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from tenants.models import Company


class RoleGrant(models.Model):
    """A node-scoped role assignment: user -> viewer/editor on some node.

    Grants can only reference nodes inside the grantee's company (enforced in
    rbac.services.grant_role).
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_grants")
    role = models.CharField(max_length=20)  # viewer | editor only (rbac.permissions)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey("content_type", "object_id")

    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="grants_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "content_type", "object_id"],
                name="uniq_role_grant",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.user} {self.role} on {self.target}"


class AuditLog(models.Model):
    """Append-only trail of RBAC-affecting actions."""

    ACTION_DELETE = "file.delete"
    ACTION_GRANT_CREATE = "grant.create"
    ACTION_GRANT_REVOKE = "grant.revoke"
    ACTION_ROLE_CHANGE = "role.change"
    ACTION_MEMBER_ADD = "member.add"
    ACTION_MEMBER_REMOVE = "member.remove"
    ACTION_WORKSPACE_CREATE = "workspace.create"
    ACTION_WORKSPACE_UPDATE = "workspace.update"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="audit_entries",
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="audit_log")
    action = models.CharField(max_length=40, db_index=True)

    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    # Free-form detail: file name, old/new role, invite code used, etc.
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.action} by {self.actor} @ {self.company_id}"
