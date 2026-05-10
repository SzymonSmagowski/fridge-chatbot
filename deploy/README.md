# apps/fridge-chatbot/deploy/

Production deployment artifacts for the apartment-building VM. Files:

| File | Runs where | Role |
|------|------------|------|
| `docker-compose.prod.yml` | VM | 13 services: caddy, fridge-backend, fridge-frontend, postgres + init, redis + init, clickhouse, minio + init, langfuse-web, langfuse-worker, livekit-server |
| `Caddyfile` | VM | Reverse proxy: `/api/*`, `/ws/*`, `/oauth/*`, `/threads/*`, `/users/*`, `/health` → backend; everything else → frontend |
| `fetch-secrets.sh` | VM | Reads 18 secrets from Secret Manager via the VM's runtime SA + writes `/srv/apps/fridge-chatbot/.env` |
| `deploy.sh` | **devcontainer** | Build + push images → SCP files to VM → run fetch-secrets → compose up |

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
- Add Langfuse organisation/project — `LANGFUSE_INIT_*` env vars in compose seed the project on first boot using the keys from Secret Manager.
- Configure HTTPS certs — when you add a domain (`var.domain`), Caddy provisions a Let's Encrypt cert automatically. Until then: HTTP only on the static IP.

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

## Langfuse UI access

Not exposed externally. SSH-tunnel:
```bash
gcloud compute ssh infra-vm --zone=europe-west1-b --project=ai-lab-493821 --tunnel-through-iap \
    -- -L 3001:langfuse-web:3000
# Then open http://localhost:3001 in your browser.
```

Login: `smagowski.szymon@gmail.com` / (the auto-generated `LANGFUSE_ADMIN_PASSWORD` from `.env` on the VM).

## Roll back

```bash
# SSH in, pin the previous SHA in .env (lines FRIDGE_BACKEND_IMAGE / FRIDGE_FRONTEND_IMAGE)
# then re-run compose up.
```

Each deploy tags with `:<git-sha>` so any historical version is one `.env` edit away.
