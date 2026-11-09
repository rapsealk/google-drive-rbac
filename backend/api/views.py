"""HTTP layer. Thin: resolve, delegate to services, map errors to status codes.

RBAC checks are explicit per endpoint via rbac.services.has_permission.
"""

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CompanyMembership, InviteCode
from accounts import services as accounts_services
from config.settings import MAX_FILE_SIZE
from files import services as files_services
from files.models import Folder, StoredFile
from files.storage import presign_get, presign_put
from rbac.models import AuditLog, RoleGrant
from rbac.permissions import (
    AUDIT_READ,
    CONTENT_READ,
    CONTENT_WRITE,
    MEMBER_MANAGE,
    SHARE_GRANT,
    WORKSPACE_MANAGE,
)
from rbac.services import grant_role, has_permission, log_action, revoke_grant
from tenants.models import Company, Workspace

from .serializers import (
    FileFinalizeSerializer,
    FilePresignSerializer,
    FileUpdateSerializer,
    FolderCreateSerializer,
    FolderUpdateSerializer,
    GrantCreateSerializer,
    LoginSerializer,
    MemberRoleSerializer,
    SignupSerializer,
    WorkspaceCreateSerializer,
    WorkspaceUpdateSerializer,
)

User = get_user_model()

NODE_MODELS = {"company": Company, "workspace": Workspace, "folder": Folder, "file": StoredFile}


def resolve_node(kind, node_id):
    return get_object_or_404(NODE_MODELS[kind], pk=node_id)


def me_data(user):
    m = getattr(user, "membership", None)
    return {
        "username": user.username,
        "email": user.email,
        "company": {"id": m.company_id, "name": m.company.name} if m else None,
        "role": m.role if m else None,
    }


def node_to_dict(obj):
    from rbac.services import iter_ancestors

    chain = list(iter_ancestors(obj))
    return {
        "kind": obj.__class__.__name__.lower(),
        "id": obj.pk,
        "name": getattr(obj, "name", str(obj)),
        "workspace_id": chain[0].workspace_id if hasattr(chain[0], "workspace_id") else None,
    }


# --- Auth ---


class SignupView(APIView):
    permission_classes = []

    def post(self, request):
        s = SignupSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            with transaction.atomic():
                if d["mode"] == "create":
                    user, _, _ = accounts_services.signup_create_company(
                        d["username"], d["email"], d["password"], d["company_name"])
                else:
                    user, _, _ = accounts_services.signup_join_company(
                        d["username"], d["email"], d["password"], d["invite_code"])
        except ValidationError as e:
            msg = "; ".join(e.messages) if hasattr(e, "messages") else str(e)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        return Response(me_data(user), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = []

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = authenticate(request, username=s.validated_data["username"],
                            password=s.validated_data["password"])
        if user is None:
            return Response({"error": "invalid credentials"}, status=status.HTTP_403_FORBIDDEN)
        login(request, user)
        return Response(me_data(user))


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({"ok": True})


class MeView(APIView):
    def get(self, request):
        return Response(me_data(request.user))


# --- Workspaces ---


class WorkspaceListCreateView(APIView):
    def get(self, request):
        m = request.user.membership
        # ponytail: lists only workspaces readable at the workspace node —
        # grants on subfolders below an otherwise-private workspace don't surface it.
        workspaces = [
            w for w in Workspace.objects.filter(company=m.company)
            if has_permission(request.user, CONTENT_READ, w)
        ]
        return Response([{"id": w.id, "name": w.name, "default_role": w.default_role} for w in workspaces])

    def post(self, request):
        if not has_permission(request.user, WORKSPACE_MANAGE, request.user.membership.company):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        s = WorkspaceCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        w = Workspace.objects.create(company=request.user.membership.company, name=s.validated_data["name"])
        log_action(actor=request.user, company=w.company, action=AuditLog.ACTION_WORKSPACE_CREATE,
                   target=w, workspace_name=w.name)
        return Response({"id": w.id, "name": w.name, "default_role": w.default_role}, status=201)


class WorkspaceDetailView(APIView):
    def patch(self, request, pk):
        w = get_object_or_404(Workspace, pk=pk)
        if not has_permission(request.user, WORKSPACE_MANAGE, w):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        s = WorkspaceUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        old_role = w.default_role
        if "name" in d:
            w.name = d["name"]
        if "default_role" in d:
            w.default_role = d["default_role"]
        w.save()
        log_action(actor=request.user, company=w.company, action=AuditLog.ACTION_WORKSPACE_UPDATE,
                   target=w, workspace_name=w.name, old_default_role=old_role, new_default_role=w.default_role)
        return Response({"id": w.id, "name": w.name, "default_role": w.default_role})


class WorkspaceContentsView(APIView):
    def get(self, request, pk):
        w = get_object_or_404(Workspace, pk=pk)
        if not has_permission(request.user, CONTENT_READ, w):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        folders = Folder.objects.filter(workspace=w, parent__isnull=True)
        files = StoredFile.objects.filter(workspace=w, folder__isnull=True)
        return Response({
            "workspace": {"id": w.id, "name": w.name, "default_role": w.default_role},
            "folders": [{"id": f.id, "name": f.name} for f in folders],
            "files": [{"id": f.id, "name": f.name, "size": f.size} for f in files],
        })


# --- Folders ---


class FolderListCreateView(APIView):
    def post(self, request):
        s = FolderCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        w = get_object_or_404(Workspace, pk=d["workspace_id"])
        parent = Folder.objects.filter(pk=d.get("parent_id"), workspace=w).first() if d.get("parent_id") else None
        try:
            folder = files_services.create_folder(request.user, w, parent, d["name"])
        except PermissionError as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"id": folder.id, "name": folder.name}, status=201)


class FolderDetailView(APIView):
    def get(self, request, pk):
        folder = get_object_or_404(Folder, pk=pk)
        if not has_permission(request.user, CONTENT_READ, folder):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response({
            "folder": {"id": folder.id, "name": folder.name, "workspace_id": folder.workspace_id,
                       "parent_id": folder.parent_id},
            "folders": [{"id": f.id, "name": f.name, "parent_id": f.parent_id} for f in folder.children.all()],
            "files": [{"id": f.id, "name": f.name, "size": f.size} for f in folder.files.all()],
        })

    def patch(self, request, pk):
        folder = get_object_or_404(Folder, pk=pk)
        s = FolderUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        parent = ...
        if "parent_id" in d:
            parent = Folder.objects.filter(pk=d["parent_id"], workspace=folder.workspace).first() \
                if d["parent_id"] else None
        try:
            folder = files_services.rename_or_move_folder(request.user, folder, d.get("name"), parent)
        except PermissionError as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": folder.id, "name": folder.name, "parent_id": folder.parent_id})

    def delete(self, request, pk):
        folder = get_object_or_404(Folder, pk=pk)
        try:
            with transaction.atomic():
                files_services.delete_folder(request.user, folder)
        except PermissionError as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True})


# --- Files ---


class FilePresignView(APIView):
    def post(self, request):
        s = FilePresignSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if d["size"] > MAX_FILE_SIZE:
            return Response({"error": "file too large (max 25MB)"}, status=status.HTTP_400_BAD_REQUEST)
        w = get_object_or_404(Workspace, pk=d["workspace_id"])
        folder = Folder.objects.filter(pk=d.get("folder_id"), workspace=w).first() if d.get("folder_id") else None
        if not has_permission(request.user, CONTENT_WRITE, folder if folder is not None else w):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        key = files_services.make_storage_key()
        return Response({
            "key": key,
            "upload_url": presign_put(key, d["content_type"]),
        }, status=201)


class FileFinalizeView(APIView):
    def post(self, request):
        s = FileFinalizeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        w = get_object_or_404(Workspace, pk=d["workspace_id"])
        folder = Folder.objects.filter(pk=d.get("folder_id"), workspace=w).first() if d.get("folder_id") else None
        try:
            f = files_services.finalize_upload(
                request.user, w, folder, d["name"], d["key"], d["size"], d["content_type"])
        except PermissionError as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": f.id, "name": f.name, "size": f.size}, status=201)


class FileDetailView(APIView):
    def get(self, request, pk):
        f = get_object_or_404(StoredFile, pk=pk)
        if not has_permission(request.user, CONTENT_READ, f):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response({"download_url": presign_get(f.storage_key), "name": f.name})

    def patch(self, request, pk):
        f = get_object_or_404(StoredFile, pk=pk)
        s = FileUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if not has_permission(request.user, CONTENT_WRITE, f):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        if "name" in d:
            f.name = d["name"]
        if "folder_id" in d:
            target_folder = Folder.objects.filter(pk=d["folder_id"], workspace=f.workspace).first() \
                if d["folder_id"] else None
            f.folder = target_folder
        f.save()
        return Response({"id": f.id, "name": f.name})

    def delete(self, request, pk):
        f = get_object_or_404(StoredFile, pk=pk)
        try:
            files_services.delete_file(request.user, f)
        except PermissionError as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True})


# --- Grants (sharing) ---


class NodeGrantsView(APIView):
    def get(self, request, kind, node_id):
        node = resolve_node(kind, node_id)
        if not has_permission(request.user, SHARE_GRANT, node):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        ct = ContentType.objects.get_for_model(type(node))
        grants = RoleGrant.objects.filter(content_type=ct, object_id=node.pk).select_related("user")
        return Response([
            {"id": g.id, "username": g.user.username, "role": g.role} for g in grants
        ])


class GrantCreateView(APIView):
    def post(self, request):
        s = GrantCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        node = resolve_node(d["kind"], d["node_id"])
        if not has_permission(request.user, SHARE_GRANT, node):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        grantee = User.objects.filter(username=d["username"]).first()
        if grantee is None:
            return Response({"error": "no such user"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            grant_role(request.user, grantee, d["role"], node)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True}, status=201)


class GrantDeleteView(APIView):
    def delete(self, request, pk):
        grant = get_object_or_404(RoleGrant, pk=pk)
        if not has_permission(request.user, SHARE_GRANT, grant.target):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        revoke_grant(request.user, grant)
        return Response({"ok": True})


# --- Members (Admin) ---


def _company_for_user(user):
    return user.membership.company


class MemberListView(APIView):
    def get(self, request):
        company = _company_for_user(request.user)
        if not (has_permission(request.user, MEMBER_MANAGE, company)
                or has_permission(request.user, SHARE_GRANT, company)):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        members = CompanyMembership.objects.filter(company=company).select_related("user")
        return Response([
            {"user_id": m.user_id, "username": m.user.username, "role": m.role} for m in members
        ])


class MemberDetailView(APIView):
    def patch(self, request, user_id):
        if not has_permission(request.user, MEMBER_MANAGE, _company_for_user(request.user)):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        s = MemberRoleSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        member_user = get_object_or_404(User, pk=user_id)
        try:
            accounts_services.change_member_role(request.user, member_user, s.validated_data["role"])
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True})

    def delete(self, request, user_id):
        if not has_permission(request.user, MEMBER_MANAGE, _company_for_user(request.user)):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        if request.user.pk == int(user_id):
            return Response({"error": "cannot remove yourself"}, status=status.HTTP_400_BAD_REQUEST)
        member_user = get_object_or_404(User, pk=user_id)
        try:
            accounts_services.remove_member(request.user, member_user)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True})


class InviteView(APIView):
    def get(self, request):
        if not has_permission(request.user, MEMBER_MANAGE, _company_for_user(request.user)):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        invites = InviteCode.objects.filter(
            company=_company_for_user(request.user), used_by__isnull=True)
        return Response([{"code": i.code, "created_at": i.created_at} for i in invites])

    def post(self, request):
        if not has_permission(request.user, MEMBER_MANAGE, _company_for_user(request.user)):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        invite = accounts_services.create_invite(request.user)
        return Response({"code": invite.code}, status=201)


# --- Audit (Admin) ---


class AuditListView(APIView):
    def get(self, request):
        if not has_permission(request.user, AUDIT_READ, _company_for_user(request.user)):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        entries = AuditLog.objects.filter(company=_company_for_user(request.user))[:200]
        return Response([
            {
                "id": e.id,
                "action": e.action,
                "actor": e.actor.username if e.actor else None,
                "metadata": e.metadata,
                "created_at": e.created_at,
            }
            for e in entries
        ])
