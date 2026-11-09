"""Signup / join / member management. Each mutating action audits."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import CompanyMembership, InviteCode
from rbac.models import AuditLog
from rbac.services import log_action

User = get_user_model()


def signup_create_company(username, email, password, company_name):
    """Create a user + their company; the creator becomes company Admin."""
    if company_name and User.objects.filter(username=username).exists():
        raise ValidationError("username already taken")
    user = User.objects.create_user(username=username, email=email or "", password=password)
    from tenants.models import Company

    company = Company.objects.create(name=company_name)
    membership = CompanyMembership.objects.create(user=user, company=company, role="admin")
    log_action(
        actor=user, company=company, action=AuditLog.ACTION_MEMBER_ADD,
        target=user, username=user.username, role="admin",
    )
    return user, company, membership


def signup_join_company(username, email, password, invite_code):
    """Create a user joining an existing company via an invite code."""
    invite = InviteCode.objects.select_related("company").filter(code=invite_code).first()
    if invite is None or invite.used_by_id is not None:
        raise ValidationError("invalid or already-used invite code")
    if User.objects.filter(username=username).exists():
        raise ValidationError("username already taken")

    user = User.objects.create_user(username=username, email=email or "", password=password)
    membership = CompanyMembership.objects.create(user=user, company=invite.company, role="user")
    invite.used_by = user
    invite.used_at = timezone.now()
    invite.save(update_fields=["used_by", "used_at"])
    log_action(
        actor=user, company=invite.company, action=AuditLog.ACTION_MEMBER_ADD,
        target=user, username=user.username, role="user",
    )
    return user, invite.company, membership


def change_member_role(actor, member_user, new_role):
    membership = CompanyMembership.objects.get(user=member_user)
    old_role = membership.role
    membership.role = new_role
    membership.save(update_fields=["role"])
    log_action(
        actor=actor, company=membership.company, action=AuditLog.ACTION_ROLE_CHANGE,
        target=member_user, username=member_user.username, old_role=old_role, new_role=new_role,
    )
    return membership


def remove_member(actor, member_user):
    membership = CompanyMembership.objects.get(user=member_user)
    company = membership.company
    membership.delete()
    log_action(
        actor=actor, company=company, action=AuditLog.ACTION_MEMBER_REMOVE,
        target=member_user, username=member_user.username,
    )


def create_invite(actor) -> InviteCode:
    membership = CompanyMembership.objects.get(user=actor)
    invite = InviteCode.objects.create(company=membership.company, created_by=actor)
    return invite
