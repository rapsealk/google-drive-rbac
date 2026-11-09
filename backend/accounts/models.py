import secrets

from django.conf import settings
from django.db import models

from tenants.models import Company


class CompanyMembership(models.Model):
    """The tenant gate: one user belongs to exactly one company."""

    ROLE_CHOICES = [
        ("admin", "admin"),
        ("user", "user"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="user")
    joined_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} @ {self.company} ({self.role})"


class InviteCode(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="invite_codes")
    code = models.CharField(max_length=12, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="invites_used",
    )
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = secrets.token_hex(4)  # 8 hex chars, unguessable enough for a toy
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} -> {self.company_id}"
