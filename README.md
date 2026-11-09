# Drive RBAC

A multi-tenant, Google-Drive-like file-sharing service whose centerpiece is a
**hand-rolled RBAC system** — no django-guardian, no django-rbac, none of
Django's built-in `Permission`/`Group`. `django.contrib.auth` is used only for
identity (users, passwords, sessions).

## Architecture

```
browser ──► nginx (static + /api/ proxy, same origin)
              └──► Django (DRF, gunicorn) ──► Postgres
                       │
                       └── presigned URLs ──► SeaweedFS (S3 API)  ◄── client PUT/GET directly
```

- **Backend** (`backend/`): Django + DRF, apps by domain — `tenants` (companies,
  workspaces), `rbac` (roles, grants, check engine, audit), `files` (folders,
  blobs, storage), `accounts` (membership, invites).
- **Frontend** (`frontend/`): React 19 + Vite + [Astryx](https://astryx.atmeta.com/)
  (StyleX), pnpm.
- **Infra**: `docker-compose.yml` — `nginx`, `web`, `postgres`, `seaweed`.

> SeaweedFS stands in for MinIO, whose free images were pulled from Docker Hub,
> quay.io and dl.min.io in 2025–2026. It speaks the same S3 API — swap back by
> changing the `seaweed` service and the `S3_ENDPOINT` / `S3_PUBLIC_ENDPOINT`
> settings only.

## Quickstart

```bash
docker compose up -d --build --wait
# app:      http://localhost:8080
# MinIO-style console: n/a (SeaweedFS master: http://localhost:9000)
```

Sign up → **Create company** (you become its Admin) → create a workspace →
upload. To let employees in, generate an invite code on the **Members** page.

## The RBAC model (locked design)

**Check engine** — a permission check walks up the resource tree
`file → folder → … → workspace → company` and takes the **union** of
permissions, **add-only** (most permissive wins, no deny rules). The engine is
framework-agnostic pure functions (`rbac/services.py`), exhaustively unit-tested.

**Roles** are code-defined constants (`rbac/permissions.py`), with a hierarchy
(admin implies editor implies viewer):

| Permission | `User` (company) | `Viewer` (node) | `Editor` (node) | `Admin` (company) |
|---|---|---|---|---|
| `content:read` (view + download) | — | ✓ | ✓ | ✓ everywhere |
| `content:write` (create/upload/rename/move) | — | — | ✓ | ✓ |
| `content:delete` (in scope) | — | — | ✓ | ✓ |
| `share:grant` (grant/revoke on nodes) | — | — | ✓ | ✓ |
| `workspace:manage` | — | — | — | ✓ |
| `member:manage` (invite, remove, roles) | — | — | — | ✓ |
| `audit:read` | — | — | — | ✓ |

- A plain `User` is **membership, not permission** — access comes entirely from
  node scopes: a workspace's `default_role` (null = private) or explicit grants.
- **Tenancy**: one user = one company. Cross-tenant grants are structurally
  impossible (validated at grant creation) and every query filters by tenant.
- **Audit**: append-only `AuditLog` for RBAC-affecting actions only
  (delete, grant/revoke, role change, member add/remove, workspace changes).
- **Uploads**: RBAC check → pre-signed PUT URL → client uploads directly to
  object storage → finalize creates the file row. Downloads: RBAC check →
  pre-signed GET.

## Tests

```bash
# backend: 33 tests — RBAC engine matrix, API permission boundaries,
# upload/download flow, audit trail
cd backend && .venv/bin/python -m pytest -q

# e2e: Playwright drives the UI over the real 4-container stack
# (self-seeds: signup → company → workspace → upload → invite → member →
#  shared access → forbidden delete → outsider isolation → audit).
# Resets the stack (drops volumes) before running.
cd frontend && pnpm e2e
```

The e2e asserts the interesting boundaries in the browser: a member with
`default_role: viewer` sees and downloads shared files, a viewer's delete is
rejected with `missing content:delete`, a user of another company sees an empty
drive, and admin-only nav is hidden from plain users.

## API summary

| Endpoint | Method | Who |
|---|---|---|
| `/api/auth/signup` `/login` `/logout` `/me` | POST/GET | anyone / anyone / logged in |
| `/api/workspaces` | GET/POST/PATCH | members / Admin |
| `/api/workspaces/{id}/contents` | GET | `content:read` on workspace |
| `/api/folders` `/folders/{id}` | GET/POST/PATCH/DELETE | `content:read/write/delete` |
| `/api/files/presign` `/finalize` | POST | `content:write` |
| `/api/files/{id}` | GET/PATCH/DELETE | `content:read/write/delete` |
| `/api/nodes/{kind}/{id}/grants`, `/api/grants` | GET/POST/DELETE | `share:grant` |
| `/api/members`, `/api/members/{user_id}` | GET/PATCH/DELETE | Admin |
| `/api/invites` | GET/POST | Admin |
| `/api/audit` | GET | Admin (`audit:read`) |

## Deliberately out (YAGNI)

JWT, deny rules, groups, runtime-custom roles, trash bin, search, file preview,
multiple companies per user, live deploy target. The S3-compatible settings mean
a real deploy is a config swap, not a rewrite.
