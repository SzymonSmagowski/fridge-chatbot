#!/usr/bin/env bash
# =============================================================================
# fetch-secrets.sh — RUNS ON THE VM (NOT your laptop)
# =============================================================================
# Reads all 18 secrets from GCP Secret Manager (using the VM's vm-runtime SA
# via the metadata server — no JSON keys, no auth files) and writes a single
# .env file at /srv/apps/fridge-chatbot/.env that docker-compose reads via
# the env_file directive.
#
# Idempotent. Re-run this every time secrets change in Secret Manager (e.g.
# after rotating a password) and then `docker compose --env-file .env up -d`.
# =============================================================================

set -euo pipefail

readonly INFRA_PROJECT="ai-lab-493821"
readonly APP_PROJECT="ai-lab-fridge-chatbot"
readonly ENV_FILE="/srv/apps/fridge-chatbot/.env"
readonly DEPLOY_DIR="/srv/apps/fridge-chatbot"

# Re-exec under sudo if not root (so /srv/apps writes succeed). Remember the
# caller's identity so we can hand the resulting .env back to them — IAP SSH
# users have generated names like `smagowski_szymon_gmail_com`, not `ubuntu`.
if [[ $EUID -ne 0 ]]; then
    exec sudo -E SUDO_USER="${USER}" "$0" "$@"
fi
readonly OWNER="${SUDO_USER:-$(id -un)}"

if ! command -v gcloud >/dev/null 2>&1; then
    echo "ERROR: gcloud not in PATH on the VM. Did the startup script run?" >&2
    exit 1
fi

mkdir -p "$DEPLOY_DIR"

get() {
    local project="$1" secret="$2"
    gcloud secrets versions access latest --secret="$secret" --project="$project" 2>/dev/null \
        || { echo "ERROR: failed to read $secret from $project" >&2; exit 1; }
}

# Read everything BEFORE writing the file — atomic-ish, never partial.
SHARED_PG=$(get "$INFRA_PROJECT" postgres-admin-password)
SHARED_REDIS=$(get "$INFRA_PROJECT" redis-password)
SHARED_CH=$(get "$INFRA_PROJECT" clickhouse-password)
SHARED_MINIO_USER=$(get "$INFRA_PROJECT" minio-root-user)
SHARED_MINIO_PASS=$(get "$INFRA_PROJECT" minio-root-password)
SHARED_LK_KEY=$(get "$INFRA_PROJECT" livekit-api-key)
SHARED_LK_SECRET=$(get "$INFRA_PROJECT" livekit-api-secret)
SHARED_LF_NEXTAUTH=$(get "$INFRA_PROJECT" langfuse-nextauth-secret)
SHARED_LF_SALT=$(get "$INFRA_PROJECT" langfuse-salt)
SHARED_LF_ENC=$(get "$INFRA_PROJECT" langfuse-encryption-key)

FRIDGE_OPENAI=$(get "$APP_PROJECT" fridge-chatbot-openai-api-key)
FRIDGE_DB=$(get "$APP_PROJECT" fridge-chatbot-db-password)
FRIDGE_REDIS=$(get "$APP_PROJECT" fridge-chatbot-redis-password)
FRIDGE_FERNET=$(get "$APP_PROJECT" fridge-chatbot-fernet-key)
FRIDGE_JWT=$(get "$APP_PROJECT" fridge-chatbot-jwt-secret-key)
FRIDGE_DEBUG=$(get "$APP_PROJECT" fridge-chatbot-backend-debug-api-key)
FRIDGE_LF_PUB=$(get "$APP_PROJECT" fridge-chatbot-langfuse-public-key)
FRIDGE_LF_SEC=$(get "$APP_PROJECT" fridge-chatbot-langfuse-secret-key)
FRIDGE_OAUTH_ID=$(get "$APP_PROJECT" fridge-chatbot-oauth-client-id)
FRIDGE_OAUTH_SECRET=$(get "$APP_PROJECT" fridge-chatbot-oauth-client-secret)

# Public base URLs.
# - PUBLIC_DOMAIN     → the user-facing fridge-chatbot app domain.
# - LANGFUSE_DOMAIN   → the operator-only Langfuse domain (fronted by Caddy).
# Both get HTTPS automatically (Caddy → Let's Encrypt).
# Override via env, e.g. LANGFUSE_DOMAIN=other.example.com ./fetch-secrets.sh
: "${PUBLIC_DOMAIN:=fridge-chatbot.duckdns.org}"
: "${LANGFUSE_DOMAIN:=smagowski-ai-lab-langfuse.duckdns.org}"
VM_IP=$(curl -fsSL -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip")
if [[ -n "$PUBLIC_DOMAIN" ]]; then
    PUBLIC_BASE_URL="https://${PUBLIC_DOMAIN}"
    # LiveKit WebSocket signaling is reverse-proxied by Caddy at /livekit-ws/*.
    # The LiveKit JS client appends /rtc/v1 to whatever serverUrl we hand it,
    # so the path here is the prefix Caddy strips before proxying to :7880.
    LIVEKIT_PUBLIC_URL="wss://${PUBLIC_DOMAIN}/livekit-ws"
else
    PUBLIC_BASE_URL="http://${VM_IP}"
    LIVEKIT_PUBLIC_URL="ws://${VM_IP}:7880"
fi
# Langfuse's NextAuth signs cookies/callbacks against this URL — it MUST match
# the URL the browser uses, or login redirects break with a 302 loop. Caddy
# terminates TLS in front of langfuse-web:3000, so the public scheme is https.
LANGFUSE_NEXTAUTH_URL_VALUE="https://${LANGFUSE_DOMAIN}"

# Image refs — caller (deploy.sh) overrides via env. Defaults to :latest.
: "${FRIDGE_BACKEND_IMAGE:=europe-west1-docker.pkg.dev/ai-lab-fridge-chatbot/fridge-chatbot/backend:latest}"
: "${FRIDGE_FRONTEND_IMAGE:=europe-west1-docker.pkg.dev/ai-lab-fridge-chatbot/fridge-chatbot/frontend:latest}"

# Admin email + langfuse admin password. Static + a fixed-but-secret default.
: "${ADMIN_EMAIL:=smagowski.szymon@gmail.com}"
LANGFUSE_ADMIN_PASSWORD="$(echo -n "${SHARED_LF_NEXTAUTH}admin" | sha256sum | cut -c1-32)"

# Backup bucket — the Terraform module postgres-backup names the bucket
# deterministically as `<app_project_id>-pg-backups`, so no Terraform-output
# round-trip needed; compose it from the project id.
BACKUP_BUCKET="${APP_PROJECT}-pg-backups"

cat > "$ENV_FILE" <<EOF
# Auto-generated by fetch-secrets.sh — DO NOT EDIT BY HAND.
# Re-run fetch-secrets.sh to refresh from Secret Manager.

# --- Image refs (override per deploy) ---
FRIDGE_BACKEND_IMAGE=${FRIDGE_BACKEND_IMAGE}
FRIDGE_FRONTEND_IMAGE=${FRIDGE_FRONTEND_IMAGE}

# --- Public URL ---
PUBLIC_BASE_URL=${PUBLIC_BASE_URL}
LIVEKIT_PUBLIC_URL=${LIVEKIT_PUBLIC_URL}
VM_EXTERNAL_IP=${VM_IP}
LANGFUSE_NEXTAUTH_URL=${LANGFUSE_NEXTAUTH_URL_VALUE}

# --- Shared infra ---
POSTGRES_ADMIN_PASSWORD=${SHARED_PG}
BACKUP_BUCKET=${BACKUP_BUCKET}
REDIS_PASSWORD=${SHARED_REDIS}
CLICKHOUSE_PASSWORD=${SHARED_CH}
MINIO_ROOT_USER=${SHARED_MINIO_USER}
MINIO_ROOT_PASSWORD=${SHARED_MINIO_PASS}
LIVEKIT_API_KEY=${SHARED_LK_KEY}
LIVEKIT_API_SECRET=${SHARED_LK_SECRET}
LANGFUSE_NEXTAUTH_SECRET=${SHARED_LF_NEXTAUTH}
LANGFUSE_SALT=${SHARED_LF_SALT}
LANGFUSE_ENCRYPTION_KEY=${SHARED_LF_ENC}
LANGFUSE_ADMIN_PASSWORD=${LANGFUSE_ADMIN_PASSWORD}
ADMIN_EMAIL=${ADMIN_EMAIL}

# --- fridge-chatbot per-app ---
FRIDGE_OPENAI_API_KEY=${FRIDGE_OPENAI}
FRIDGE_DB_PASSWORD=${FRIDGE_DB}
FRIDGE_REDIS_PASSWORD=${FRIDGE_REDIS}
FRIDGE_FERNET_KEY=${FRIDGE_FERNET}
FRIDGE_JWT_SECRET_KEY=${FRIDGE_JWT}
FRIDGE_BACKEND_DEBUG_API_KEY=${FRIDGE_DEBUG}
FRIDGE_LANGFUSE_PUBLIC_KEY=${FRIDGE_LF_PUB}
FRIDGE_LANGFUSE_SECRET_KEY=${FRIDGE_LF_SEC}
FRIDGE_GOOGLE_CLIENT_ID=${FRIDGE_OAUTH_ID}
FRIDGE_GOOGLE_CLIENT_SECRET=${FRIDGE_OAUTH_SECRET}
EOF

chmod 600 "$ENV_FILE"
chown "$OWNER":"$(id -gn "$OWNER")" "$ENV_FILE"

echo "Wrote $ENV_FILE ($(grep -cE '^[A-Z]' "$ENV_FILE") values)"
echo "VM external IP: $VM_IP"
