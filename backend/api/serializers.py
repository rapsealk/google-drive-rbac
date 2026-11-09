from rest_framework import serializers


class SignupSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["create", "join"])
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(min_length=8, write_only=True)
    company_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    invite_code = serializers.CharField(max_length=12, required=False, allow_blank=True, default="")


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class WorkspaceCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)


class WorkspaceUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    default_role = serializers.ChoiceField(choices=["", "viewer", "editor"], required=False)


class FolderCreateSerializer(serializers.Serializer):
    workspace_id = serializers.IntegerField()
    parent_id = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(max_length=255)


class FolderUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    parent_id = serializers.IntegerField(required=False, allow_null=True)


class FilePresignSerializer(serializers.Serializer):
    workspace_id = serializers.IntegerField()
    folder_id = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(max_length=255)
    size = serializers.IntegerField(min_value=1)
    content_type = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class FileFinalizeSerializer(serializers.Serializer):
    workspace_id = serializers.IntegerField()
    folder_id = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(max_length=255)
    key = serializers.CharField(max_length=100)
    size = serializers.IntegerField(min_value=0)
    content_type = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class FileUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    folder_id = serializers.IntegerField(required=False, allow_null=True)


class GrantCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["company", "workspace", "folder", "file"])
    node_id = serializers.IntegerField()
    username = serializers.CharField()
    role = serializers.ChoiceField(choices=["viewer", "editor"])


class MemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["admin", "user"])
