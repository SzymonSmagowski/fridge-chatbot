#!/usr/bin/env bash
# =============================================================================
# deploy.sh — RUNS FROM YOUR DEVCONTAINER (not the VM)
# =============================================================================
# 1. Builds backend + frontend Docker images, tagged with the current git SHA
# 2. Pushes them to Artifact Registry
# 3. Copies docker-compose.prod.yml + Caddyfile + fetch-secrets.sh to the VM
# 4. Runs fetch-secrets.sh on the VM (populates /srv/apps/fridge-chatbot/.env)
# 5. `docker compose pull` + `up -d` on the VM
# 6. Reports the public URL
#
# Idempotent. Re-run after every code change.
# =============================================================================

set -euo pipefail
cd "$(dirname "$0")"
readonly DEPLOY_DIR="$PWD"
readonly APP_DIR="$(realpath "$DEPLOY_DIR/..")"

readonly VM_NAME="infra-vm"
readonly VM_ZONE="europe-west1-b"
readonly INFRA_PROJECT="ai-lab-493821"
readonly APP_PROJECT="ai-lab-fridge-chatbot"
readonly REGION="europe-west1"
readonly REGISTRY="${REGION}-docker.pkg.dev/${APP_PROJECT}/fridge-chatbot"

# Tag images with git SHA + :latest (so rollback is `docker tag <sha> :latest && pull`).
# If the working tree has uncommitted changes the build wouldn't match the SHA,
# so append `-dirty` to make that visible in `docker images`.
TAG="$(git rev-parse --short=12 HEAD)"
if ! git diff --quiet HEAD -- "$APP_DIR" "$DEPLOY_DIR"; then
    TAG="${TAG}-dirty"
fi
BACKEND_IMG="${REGISTRY}/backend:${TAG}"
FRONTEND_IMG="${REGISTRY}/frontend:${TAG}"
BACKEND_LATEST="${REGISTRY}/backend:latest"
FRONTEND_LATEST="${REGISTRY}/frontend:latest"

echo "==> Tag: $TAG"

# --- 1. Build + push images via Cloud Build ----------------------------------
# Devcontainers don't have docker-in-docker, so we use Cloud Build instead:
# upload the source, GCP builds the image and pushes it to Artifact Registry.
# Free tier: 120 build-min/day. Default Cloud Build SA needs writer access
# on the per-app repo (granted via Terraform module "container_registry").
#
# `--tag <sha>` is the only image tag that Cloud Build supports natively;
# we alias `:latest` afterward via `gcloud artifacts docker tags add`
# (no rebuild — just a tag update, instant + free).

echo "==> Cloud Build: backend ($BACKEND_IMG)"
gcloud builds submit \
    --tag "$BACKEND_IMG" \
    --project="$APP_PROJECT" \
    --timeout=15m \
    "$APP_DIR/backend"

echo "==> Cloud Build: frontend ($FRONTEND_IMG)"
gcloud builds submit \
    --tag "$FRONTEND_IMG" \
    --project="$APP_PROJECT" \
    --timeout=20m \
    "$APP_DIR/frontend"

echo "==> Tag :latest on both images"
gcloud artifacts docker tags add "$BACKEND_IMG"  "$BACKEND_LATEST"  --quiet
gcloud artifacts docker tags add "$FRONTEND_IMG" "$FRONTEND_LATEST" --quiet

# --- 3. Copy deploy artifacts to VM ------------------------------------------
# IAP SSH uses an OS-Login-generated user (e.g. smagowski_szymon_gmail_com),
# not `ubuntu`. The next step's `scp` overwrites four specific files in
# /srv/apps/fridge-chatbot/ — we chown only those (plus the dir) to the
# connecting user so scp can write directly.
#
# DO NOT `chown -R /srv/apps/fridge-chatbot` here. The same path also holds
# `data/` — Docker bind-mount roots for postgres, redis, clickhouse, minio.
# A recursive chown reassigns Postgres's data files away from UID 70 and
# the database silently bricks itself on the next new connection
# (`could not open file "global/pg_filenode.map": Permission denied`).
# See incident 2026-05-12: chown -R wiped postgres ownership during a
# deploy retry. Recovery requires `sudo chown -R 70:70 data/postgres`
# and a postgres restart.
#
# `touch` first so a fresh VM (where the files don't exist yet) doesn't
# error on the chown; touch is a no-op when the file already exists.
echo "==> Copy compose/Caddyfile/fetch-secrets.sh to VM"
gcloud compute ssh "$VM_NAME" --zone="$VM_ZONE" --project="$INFRA_PROJECT" \
    --tunnel-through-iap --quiet \
    --command='set -e
        sudo mkdir -p /srv/apps/fridge-chatbot
        sudo touch \
            /srv/apps/fridge-chatbot/docker-compose.prod.yml \
            /srv/apps/fridge-chatbot/Caddyfile \
            /srv/apps/fridge-chatbot/fetch-secrets.sh \
            /srv/apps/fridge-chatbot/provision-langfuse-org.sh
        sudo chown "$(id -un)":"$(id -gn)" \
            /srv/apps/fridge-chatbot \
            /srv/apps/fridge-chatbot/docker-compose.prod.yml \
            /srv/apps/fridge-chatbot/Caddyfile \
            /srv/apps/fridge-chatbot/fetch-secrets.sh \
            /srv/apps/fridge-chatbot/provision-langfuse-org.sh
    '

gcloud compute scp --tunnel-through-iap \
    --zone="$VM_ZONE" --project="$INFRA_PROJECT" \
    docker-compose.prod.yml Caddyfile fetch-secrets.sh provision-langfuse-org.sh \
    "$VM_NAME:/srv/apps/fridge-chatbot/"

# --- 4. Fetch secrets + 5. compose up on VM ----------------------------------
# `gcloud auth configure-docker` writes a credHelpers entry pointing at the
# `docker-credential-gcloud` binary (ships with the SDK). The helper asks the
# metadata server for an OAuth token at pull time — no JSON keys, no
# `docker login`. Idempotent: re-running just rewrites the same JSON.
echo "==> Run fetch-secrets.sh + docker compose up -d on VM"
gcloud compute ssh "$VM_NAME" --zone="$VM_ZONE" --project="$INFRA_PROJECT" \
    --tunnel-through-iap --quiet \
    --command="
        set -e
        cd /srv/apps/fridge-chatbot
        chmod +x fetch-secrets.sh provision-langfuse-org.sh
        sudo gcloud auth configure-docker '${REGION}-docker.pkg.dev' --quiet
        FRIDGE_BACKEND_IMAGE='$BACKEND_IMG' \
        FRIDGE_FRONTEND_IMAGE='$FRONTEND_IMG' \
        sudo -E ./fetch-secrets.sh
        sudo docker compose -f docker-compose.prod.yml --env-file .env pull
        sudo docker compose -f docker-compose.prod.yml --env-file .env up -d
        # One-shot, idempotent: rename the legacy 'prodorg' Langfuse org to
        # the per-app 'fridge-chatbot' org. No-op on subsequent re-deploys.
        sudo ./provision-langfuse-org.sh
    "

# --- 6. Report public URL ----------------------------------------------------
VM_IP=$(gcloud compute instances describe "$VM_NAME" \
    --zone="$VM_ZONE" --project="$INFRA_PROJECT" \
    --format='value(networkInterfaces[0].accessConfigs[0].natIP)')
echo
echo "Deployed: http://${VM_IP}/"
echo "Tag: ${TAG}"
echo "Backend image: ${BACKEND_IMG}"
echo "Frontend image: ${FRONTEND_IMG}"
