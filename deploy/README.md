# apps/fridge-chatbot/deploy/

Production deployment artifacts for the apartment-building VM. Files:

| File | Runs where | Role |
|------|------------|------|
| `docker-compose.prod.yml` | VM | 13 services: caddy, fridge-backend, fridge-frontend, postgres + init, redis + init, clickhouse, minio + init, langfuse-web, langfuse-worker, livekit-server |
| `Caddyfile` | VM | Two virtualhosts. `fridge-chatbot.smagowskiai.dev` → backend/frontend/livekit (path-based). `langfuse.smagowskiai.dev` → `langfuse-web:3000` (operator UI, self-signup off). |
| `fetch-secrets.sh` | VM | Reads 18 secrets from Secret Manager via the VM's runtime SA + writes `/srv/apps/fridge-chatbot/.env` |
| `provision-langfuse-org.sh` | VM | One-shot, idempotent: migrates the legacy `prodorg` Langfuse org → per-app `fridge-chatbot` org via direct SQL on the `langfuse` Postgres DB. |
| `deploy.sh` | **devcontainer** | Build + push images → SCP files to VM → run fetch-secrets → compose up → run provision-langfuse-org |

## First deploy

```bash
cd apps/fridge-chatbot/deploy
./deploy.sh
```

This builds + pushes `:latest` and `:<git-sha>` for both backend and frontend, copies the three deploy files to the VM, runs `fetch-secrets.sh` on the VM, and brings the stack up. The Caddy container exposes `:80` on the VM's static IP — the public URL is printed at the end.

## Subsequent deploys

Same command. Idempotent. New images get a new git-sha tag; `:latest` updates too.

## Per-app DB / Redis user creation

`docker-compose.prod.yml` includes `postgres-init` and `redis-init` one-shot containers that create the `fridge_chatbot` Postgres user/DB and the `fridge-chatbot` Redis ACL user automatically — using passwords pulled from Secret Manager via `.env`. No manual SQL needed.

If you add a second app (`portfolio` etc.), the cleanest pattern is to extend `postgres-init` and `redis-init` with another step, OR run `terraform/scripts/bootstrap-app-db.sh portfolio` + `bootstrap-app-redis.sh portfolio` from your devcontainer (one-off).

## What you DON'T need to do manually

- Run any psql / redis-cli to create users — the init containers handle it.
- Add Langfuse organisation/project — on a **fresh VM**, `LANGFUSE_INIT_*` env vars in compose seed the per-app org (`fridge-chatbot`) + project (`fridge-chatbot`) + admin user on first boot using the keys from Secret Manager. On an **existing VM** that was previously seeded under the legacy `prodorg` name, `provision-langfuse-org.sh` migrates it on next deploy (idempotent, runs every deploy, no-ops after the first success).
- Configure HTTPS certs — Caddy provisions Let's Encrypt certs automatically for every `<host>.smagowskiai.dev` virtualhost the first time it's hit. DNS is hosted at Cloudflare; records are set to "DNS only" (gray cloud) so HTTP-01 ACME works. See `docs/cloud-engineer-runbook.md` "Pending: operational improvements" for the eventual Cloudflare-proxy + DNS-01 upgrade.

## What you DO need to do manually

- **Update the OAuth client's authorized redirect URI** in the GCP console after first deploy — it must include `http://<VM_IP>/oauth/google/callback`. The local-dev URI (`http://localhost:8001/...`) is already there.

## Logs

Per-container logs:
```bash
gcloud compute ssh infra-vm --zone=europe-west1-b --project=ai-lab-493821 --tunnel-through-iap \
    -- 'sudo docker compose -f /srv/apps/fridge-chatbot/docker-compose.prod.yml logs -f fridge-backend'
```

Or via Cloud Logging (Ops Agent ships container stdout):
- https://console.cloud.google.com/logs/query?project=ai-lab-493821

## Langfuse UI access (operator)

Open in any browser:

    https://langfuse.smagowskiai.dev

Login: `smagowski.szymon@gmail.com` / (the auto-generated `LANGFUSE_ADMIN_PASSWORD` from `.env` on the VM — read it with `gcloud compute ssh infra-vm --tunnel-through-iap -- 'sudo grep LANGFUSE_ADMIN_PASSWORD /srv/apps/fridge-chatbot/.env'`).

Self-signup is disabled (`AUTH_DISABLE_SIGNUP=true` in compose). Only the seeded admin can sign in; additional operators must be invited from inside the UI.

SSH tunnels (`gcloud compute ssh ... -L 3001:langfuse-web:3000`) are no longer the recommended access path — the web-first hostname above replaces them.

## Operator DB access (Postgres + Redis from your laptop)

Postgres and Redis bind to the VM's public IP on their standard ports, but
reachability is gated by a GCP firewall rule that allows tcp:5432 + tcp:6379
**only from the operator's residential /32** (`var.operator_whitelist_ips` in
`terraform/prod.auto.tfvars`). The world sees nothing; only the operator's
home network does.

| Service | Host | Port | TLS | Auth |
|---|---|---|---|---|
| Postgres | `34.53.156.72` | `5432` | off (single-operator trade-off; see compose comments) | password |
| Redis | `34.53.156.72` | `6379` | off | password (+ optional per-app ACL user) |

### Retrieve credentials

```bash
# Per-app DB password (use with username `fridge_chatbot`, db `fridge_chatbot`)
gcloud secrets versions access latest \
  --secret=fridge-chatbot-db-password \
  --project=ai-lab-fridge-chatbot

# Per-app Redis password (use with username `fridge-chatbot`)
gcloud secrets versions access latest \
  --secret=fridge-chatbot-redis-password \
  --project=ai-lab-fridge-chatbot

# Postgres ADMIN password (use with username `postgres`; needed to reach the
# `langfuse` DB or to manage roles across apps). Lives in the infra project,
# NOT the app project.
gcloud secrets versions access latest \
  --secret=postgres-admin-password \
  --project=ai-lab-493821

# Redis root password (use with default user; needed to manage ACLs).
gcloud secrets versions access latest \
  --secret=redis-password \
  --project=ai-lab-493821
```

### pgAdmin / DBeaver connection profile

- Host: `34.53.156.72`
- Port: `5432`
- Maintenance DB (admin): `postgres` / DB to explore: `fridge_chatbot` or `langfuse`
- Username: `fridge_chatbot` (app data) or `postgres` (admin / Langfuse data)
- Password: see commands above
- SSL mode: `prefer` is fine; `require` will fail until TLS is enabled

### redis-cli

```bash
# Per-app ACL user (recommended)
redis-cli -h 34.53.156.72 -p 6379 --user fridge-chatbot \
  --pass "$(gcloud secrets versions access latest --secret=fridge-chatbot-redis-password --project=ai-lab-fridge-chatbot)"

# Or root (ACL management)
redis-cli -h 34.53.156.72 -p 6379 \
  -a "$(gcloud secrets versions access latest --secret=redis-password --project=ai-lab-493821)"
```

### If your home IP changes

Update `operator_whitelist_ips` in `terraform/prod.auto.tfvars` and re-apply:

```bash
cd terraform && terraform apply
```

The docker-compose port-mapping does not need to change; only the firewall
rule's `source_ranges` do.

## Per-app Langfuse org + project pattern

One Langfuse org per app, one project per app. App `<slug>` lives under org id `<slug>` containing project id `<slug>`. Trace keys live in Secret Manager as `<slug>-langfuse-public-key` / `<slug>-langfuse-secret-key`.

To add Langfuse to a new app `<slug>`:

1. Generate `<slug>-langfuse-public-key` + `<slug>-langfuse-secret-key` in the app's GCP project Secret Manager (already automated by `terraform/scripts/seed-secrets.sh`).
2. In the app's `docker-compose.prod.yml`, set the same `LANGFUSE_INIT_*` block as `apps/fridge-chatbot/deploy/docker-compose.prod.yml` but with `<slug>` everywhere.
3. Copy `apps/fridge-chatbot/deploy/provision-langfuse-org.sh` to `apps/<slug>/deploy/`. Change the four `TARGET_*` + `LEGACY_*` constants near the top. If the app has never been deployed before, set `LEGACY_ORG_ID` to a value that doesn't exist (e.g. the same as `TARGET_ORG_ID`) — the script will recognise that and no-op.
4. Have the app's `deploy.sh` invoke `provision-langfuse-org.sh` after `docker compose up -d`.

Why this pattern and not the Langfuse Admin API? The Instance Management API (Bearer `ADMIN_API_KEY`) that handles org CRUD is Enterprise-only. The OSS-accessible org-scoped Admin API requires a UI-minted org API key, which violates the zero-clicks contract. Direct SQL against the `langfuse` Postgres DB is reliable, transactional, and gated by a schema-introspection check that aborts cleanly on Langfuse schema drift.

## Roll back

```bash
# SSH in, pin the previous SHA in .env (lines FRIDGE_BACKEND_IMAGE / FRIDGE_FRONTEND_IMAGE)
# then re-run compose up.
```

Each deploy tags with `:<git-sha>` so any historical version is one `.env` edit away.
