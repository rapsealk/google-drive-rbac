from django.db import models

from tenants.models import Workspace


class Folder(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="folders")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "parent", "name"],
                name="uniq_folder_name_per_parent",
            ),
        ]

    def __str__(self):
        return self.name

    def get_parent_node(self):
        # Root folders (parent=None) hang off the workspace itself.
        return self.parent if self.parent_id is not None else self.workspace


class StoredFile(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="files")
    folder = models.ForeignKey(Folder, null=True, blank=True, on_delete=models.CASCADE, related_name="files")
    name = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=100, unique=True)  # "uploads/<uuid>"
    size = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def get_parent_node(self):
        # Root files (folder=None) hang off the workspace itself.
        return self.folder if self.folder_id is not None else self.workspace
