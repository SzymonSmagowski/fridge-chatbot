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
TAG="$(git rev-parse --short=12 HEAD)"
BACKEND_IMG="${REGISTRY}/backend:${TAG}"
FRONTEND_IMG="${REGISTRY}/frontend:${TAG}"
BACKEND_LATEST="${REGISTRY}/backend:latest"
FRONTEND_LATEST="${REGISTRY}/frontend:latest"

echo "==> Tag: $TAG"

# --- 1. Authenticate Docker to Artifact Registry (once per session) ----------
echo "==> docker login (Artifact Registry)"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet >/dev/null

# --- 2. Build + push images --------------------------------------------------
echo "==> Build backend image"
docker build \
    -t "$BACKEND_IMG" -t "$BACKEND_LATEST" \
    -f "$APP_DIR/backend/Dockerfile" "$APP_DIR/backend"

echo "==> Build frontend image"
docker build \
    -t "$FRONTEND_IMG" -t "$FRONTEND_LATEST" \
    -f "$APP_DIR/frontend/Dockerfile" "$APP_DIR/frontend"

echo "==> Push images"
docker push "$BACKEND_IMG"
docker push "$BACKEND_LATEST"
docker push "$FRONTEND_IMG"
docker push "$FRONTEND_LATEST"

# --- 3. Copy deploy artifacts to VM ------------------------------------------
echo "==> Copy compose/Caddyfile/fetch-secrets.sh to VM"
gcloud compute ssh "$VM_NAME" --zone="$VM_ZONE" --project="$INFRA_PROJECT" \
    --tunnel-through-iap --quiet \
    --command='sudo mkdir -p /srv/apps/fridge-chatbot && sudo chown ubuntu:ubuntu /srv/apps/fridge-chatbot'

gcloud compute scp --tunnel-through-iap \
    --zone="$VM_ZONE" --project="$INFRA_PROJECT" \
    docker-compose.prod.yml Caddyfile fetch-secrets.sh \
    "$VM_NAME:/srv/apps/fridge-chatbot/"

# --- 4. Fetch secrets + 5. compose up on VM ----------------------------------
echo "==> Run fetch-secrets.sh + docker compose up -d on VM"
gcloud compute ssh "$VM_NAME" --zone="$VM_ZONE" --project="$INFRA_PROJECT" \
    --tunnel-through-iap --quiet \
    --command="
        set -e
        cd /srv/apps/fridge-chatbot
        chmod +x fetch-secrets.sh
        FRIDGE_BACKEND_IMAGE='$BACKEND_IMG' \
        FRIDGE_FRONTEND_IMAGE='$FRONTEND_IMG' \
        sudo -E ./fetch-secrets.sh
        sudo docker compose -f docker-compose.prod.yml --env-file .env pull
        sudo docker compose -f docker-compose.prod.yml --env-file .env up -d
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
