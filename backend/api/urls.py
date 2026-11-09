from django.urls import path

from . import views

urlpatterns = [
    path("auth/signup", views.SignupView.as_view()),
    path("auth/login", views.LoginView.as_view()),
    path("auth/logout", views.LogoutView.as_view()),
    path("auth/me", views.MeView.as_view()),

    path("workspaces", views.WorkspaceListCreateView.as_view()),
    path("workspaces/<int:pk>", views.WorkspaceDetailView.as_view()),
    path("workspaces/<int:pk>/contents", views.WorkspaceContentsView.as_view()),

    path("folders", views.FolderListCreateView.as_view()),
    path("folders/<int:pk>", views.FolderDetailView.as_view()),

    path("files/presign", views.FilePresignView.as_view()),
    path("files/finalize", views.FileFinalizeView.as_view()),
    path("files/<int:pk>", views.FileDetailView.as_view()),

    path("nodes/<str:kind>/<int:node_id>/grants", views.NodeGrantsView.as_view()),
    path("grants", views.GrantCreateView.as_view()),
    path("grants/<int:pk>", views.GrantDeleteView.as_view()),

    path("members", views.MemberListView.as_view()),
    path("members/<int:user_id>", views.MemberDetailView.as_view()),
    path("invites", views.InviteView.as_view()),

    path("audit", views.AuditListView.as_view()),
]
