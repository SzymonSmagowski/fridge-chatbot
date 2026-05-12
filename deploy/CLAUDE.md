# deploy/

Production deployment artifacts for the apartment VM. See `README.md` for the operator-facing usage (commands, credentials, runbook). This file is for AI assistants reading the code.

## Hard rules — read before editing `deploy.sh`

### Never `chown -R /srv/apps/<app>/` on the VM

The VM keeps each app's deploy artifacts **and** its Docker bind-mount data under the same path:

```
/srv/apps/fridge-chatbot/
├── docker-compose.prod.yml      ← scp target
├── Caddyfile                    ← scp target
├── fetch-secrets.sh             ← scp target
├── provision-langfuse-org.sh    ← scp target
├── .env                         ← created by fetch-secrets.sh on the VM
└── data/                        ← Docker bind-mount root
    ├── postgres/                ← owned by UID 70  (alpine postgres user)
    ├── redis/                   ← owned by UID 999
    ├── clickhouse/              ← owned by UID 101
    ├── minio/                   ← owned by UID 1000
    └── caddy/                   ← owned by root
```

`sudo chown -R "$(id -un)" /srv/apps/fridge-chatbot/` reassigns every file under `data/` to the OS Login UID. Postgres logs `could not open file "global/pg_filenode.map": Permission denied` on the next new connection and refuses every query. Other services follow on their next restart (Spot preemption guarantees this).

**Recovery if it happens:** `sudo docker compose stop postgres && sudo chown -R 70:70 /srv/apps/fridge-chatbot/data/postgres && sudo docker compose up -d`. Same pattern for the other services with their respective UIDs.

**How `deploy.sh` does it correctly:** the pre-scp step `touch`es each of the four expected files, then chowns *only those four files plus the dir itself* — never `-R`, never anything under `data/`. If you ever add a new file to the scp list, add it to the `touch` and `chown` blocks too.

### Origin

Incident 2026-05-12: a recursive chown during a deploy retry bricked Postgres in production for ~5 min. Recovery commands above. The deploy.sh comment block at the chown step retains the same warning inline.

## TODOs

- **Parallelize Cloud Builds.** `deploy.sh` runs `gcloud builds submit` for backend then for frontend serially (~13 min wall clock). Cloud Build's default concurrent-build limit is 10/project — background both + `wait` cuts wall clock to ~max(backend, frontend) ≈ 8 min. Same total build-minutes, no cost change. Refactor when next touching deploy.sh, or when adding a third build target (image scan etc.).
