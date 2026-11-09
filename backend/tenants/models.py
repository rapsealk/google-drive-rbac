from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def get_parent_node(self):
        return None


class Workspace(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="workspaces")
    name = models.CharField(max_length=200)
    # Role granted to every company member at this workspace; null = private.
    # One of rbac.permissions.ROLE_VIEWER / ROLE_EDITOR, or empty.
    default_role = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_workspace_name_per_company"),
        ]

    def __str__(self):
        return self.name

    def get_parent_node(self):
        return self.company
