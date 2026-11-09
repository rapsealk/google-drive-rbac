"""File/folder mutations. Every action checks RBAC and audits deletes."""

import uuid

from django.core.exceptions import ValidationError

from files import storage
from files.models import Folder, StoredFile
from rbac.models import AuditLog
from rbac.permissions import CONTENT_DELETE, CONTENT_WRITE
from rbac.services import has_permission, log_action


def _check(user, perm, node):
    if not has_permission(user, perm, node):
        raise PermissionError(f"missing {perm} on {node}")


def make_storage_key() -> str:
    return f"uploads/{uuid.uuid4()}"


def create_folder(actor, workspace, parent, name) -> Folder:
    _check(actor, CONTENT_WRITE, parent if parent is not None else workspace)
    return Folder.objects.create(workspace=workspace, parent=parent, name=name)


def rename_or_move_folder(actor, folder: Folder, name=None, parent=... ) -> Folder:
    _check(actor, CONTENT_WRITE, folder)
    if name is not None:
        folder.name = name
    if parent is not ...:
        if parent is not None:
            if parent.workspace_id != folder.workspace_id:
                raise ValidationError("cannot move between workspaces")
            # Cycle check: parent must not be inside the folder itself.
            from rbac.services import iter_ancestors

            ancestor_ids = {a.pk for a in iter_ancestors(parent) if isinstance(a, Folder)}
            if folder.pk in ancestor_ids:
                raise ValidationError("cannot move a folder into itself")
        folder.parent = parent
    folder.save()
    return folder


def delete_folder(actor, folder: Folder):
    """Recursively delete the subtree: all blobs, then all rows. Audited per file."""
    _check(actor, CONTENT_DELETE, folder)
    _delete_folder_tree(actor, folder)


def _delete_folder_tree(actor, folder):
    for child in folder.children.all():
        _delete_folder_tree(actor, child)
    for f in list(folder.files.all()):
        delete_file(actor, f, check=False)
    folder.delete()


def finalize_upload(actor, workspace, folder, name, key, size, content_type) -> StoredFile:
    _check(actor, CONTENT_WRITE, folder if folder is not None else workspace)
    if not key.startswith("uploads/") or "/" in key[len("uploads/"):]:
        raise ValidationError("invalid storage key")
    return StoredFile.objects.create(
        workspace=workspace, folder=folder, name=name,
        storage_key=key, size=size, content_type=content_type or "",
    )


def delete_file(actor, f: StoredFile, check=True):
    if check:
        _check(actor, CONTENT_DELETE, f)
    storage.delete_object(f.storage_key)
    log_action(
        actor=actor, company=f.workspace.company, action=AuditLog.ACTION_DELETE,
        target=f, file_name=f.name, storage_key=f.storage_key,
    )
    f.delete()
