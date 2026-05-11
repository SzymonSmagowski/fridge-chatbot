#!/usr/bin/env bash
# =============================================================================
# provision-langfuse-org.sh — RUNS ON THE VM
# =============================================================================
# One-shot, idempotent migration of the existing Langfuse org from the legacy
# seed id (`prodorg` / "Production") to the per-app id (`fridge-chatbot` /
# "Fridge Chatbot"). Required because Langfuse's headless init (LANGFUSE_INIT_*
# env vars) only seeds resources on FIRST boot. The compose file has been
# updated to use the new names so a fresh VM seeds correctly out-of-the-box;
# this script is purely for migrating the CURRENT VM whose org was already
# seeded under the old name.
#
# Why direct SQL and not the Langfuse Admin API?
#   - The Langfuse Instance Management API (Bearer $ADMIN_API_KEY) that handles
#     org CRUD is Enterprise-Edition only. We run the OSS image
#     (langfuse/langfuse:3) and won't pay for EE.
#   - The OSS-accessible org-scoped Admin API (Basic-Auth org keys) can rename
#     PROJECTS but not the org itself, and the org key has to be minted from
#     the UI by an authenticated admin — which violates the "zero manual UI
#     clicks" contract for this dispatch.
#   - SQL is one transaction against the `langfuse` Postgres DB, gated by a
#     schema-introspection check that aborts cleanly if column names drift in
#     a future Langfuse release.
#
# Per-app pattern (future apps):
#   Each app owns its own provision-langfuse-org.sh under apps/<app>/deploy/.
#   Copy this script, change the three TARGET_* values + LEGACY_ORG_ID, and
#   commit. After the app's first deploy the script is run once (manually or
#   via the app's deploy.sh hook) to migrate or no-op based on idempotency.
# =============================================================================

set -euo pipefail

readonly TARGET_ORG_ID="fridge-chatbot"
readonly TARGET_ORG_NAME="Fridge Chatbot"
readonly TARGET_PROJECT_ID="fridge-chatbot"
readonly LEGACY_ORG_ID="prodorg"
readonly COMPOSE_FILE="/srv/apps/fridge-chatbot/docker-compose.prod.yml"
readonly ENV_FILE="/srv/apps/fridge-chatbot/.env"

# Re-exec under sudo so we can call docker (membership in the docker group
# isn't guaranteed for IAP-SSH OS-Login users).
if [[ $EUID -ne 0 ]]; then
    exec sudo -E "$0" "$@"
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE missing — run fetch-secrets.sh first." >&2
    exit 1
fi

# Source the env file to get POSTGRES_ADMIN_PASSWORD. The .env is `KEY=VALUE`
# with no quoting; safe to source.
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

# --- 1. Wait for langfuse-web health (Caddy may proxy before app is ready) ---
# We probe from inside the `caddy` container (alpine, has wget) over the
# `apartment` Docker network — same path Caddy itself uses for proxying.
# Langfuse-web does Prisma migrations + ClickHouse warmup on a fresh boot
# and can take ~90-120s on a Spot VM; 180s gives generous headroom.
echo "==> Waiting for langfuse-web /api/public/health ..."
for i in $(seq 1 180); do
    body="$(docker compose -f "$COMPOSE_FILE" exec -T caddy \
        wget -q -O - http://langfuse-web:3000/api/public/health 2>/dev/null || true)"
    if [[ "$body" == *'"status":"OK"'* ]]; then
        echo "    langfuse-web healthy ($body)."
        break
    fi
    if [[ $i -eq 180 ]]; then
        echo "ERROR: langfuse-web did not become healthy in 180s." >&2
        exit 1
    fi
    sleep 1
done

# --- 2. Run the migration SQL ----------------------------------------------
# Why a shell-quoted heredoc with `psql -v ON_ERROR_STOP=1`: any failure (FK
# violation, missing column, etc.) returns non-zero and the outer `set -e`
# aborts before any half-applied state lands. The DO block wraps the rename
# in a single transaction with the idempotency check inline.

echo "==> Migrating Langfuse org (legacy=$LEGACY_ORG_ID → target=$TARGET_ORG_ID)"

docker compose -f "$COMPOSE_FILE" exec -T -e PGPASSWORD="$POSTGRES_ADMIN_PASSWORD" \
    postgres psql -v ON_ERROR_STOP=1 -h localhost -U postgres -d langfuse <<SQL
-- Bail loudly if Langfuse's schema has drifted from what this script expects.
-- We touch organizations.id, organizations.name, and assume projects.org_id
-- is the FK column linking projects to their owning org.
DO \$\$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'organizations' AND column_name = 'id'
    ) THEN
        RAISE EXCEPTION 'organizations.id column not found — Langfuse schema changed';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'projects' AND column_name = 'org_id'
    ) THEN
        RAISE EXCEPTION 'projects.org_id column not found — Langfuse schema changed';
    END IF;
END
\$\$;

-- Migration state machine. Handles three states:
--   A. Only legacy org exists       → create target, move project + memberships, delete legacy
--   B. Both orgs exist (split)      → move project + memberships from legacy to target, delete legacy.
--                                     Happens when langfuse-web restart re-ran headless init under
--                                     the new LANGFUSE_INIT_ORG_ID before this script ran.
--   C. Only target org exists       → nothing to do (fresh VM or already-migrated)
--   D. Neither exists               → nothing to do (first-boot will seed via LANGFUSE_INIT_*)
-- For B, dedupe memberships first: if the same (user, role) pair already
-- exists on the target org, drop the duplicate row on the legacy org rather
-- than copying it (the UNIQUE constraint on (user_id, org_id) would otherwise
-- fire on UPDATE).
DO \$\$
DECLARE
    target_exists boolean;
    legacy_exists boolean;
    memberships_table_exists boolean;
BEGIN
    SELECT EXISTS(SELECT 1 FROM organizations WHERE id = '${TARGET_ORG_ID}') INTO target_exists;
    SELECT EXISTS(SELECT 1 FROM organizations WHERE id = '${LEGACY_ORG_ID}') INTO legacy_exists;
    SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'organization_memberships')
        INTO memberships_table_exists;

    IF NOT legacy_exists AND NOT target_exists THEN
        RAISE NOTICE 'no legacy or target org present — first-boot will seed via LANGFUSE_INIT_*.';
        RETURN;
    END IF;

    IF NOT legacy_exists AND target_exists THEN
        RAISE NOTICE 'target org "${TARGET_ORG_ID}" already in place; nothing to migrate.';
        RETURN;
    END IF;

    -- legacy_exists from here. Make sure target exists (create if not).
    IF NOT target_exists THEN
        INSERT INTO organizations (id, name, created_at, updated_at)
        VALUES (
            '${TARGET_ORG_ID}',
            '${TARGET_ORG_NAME}',
            (SELECT created_at FROM organizations WHERE id = '${LEGACY_ORG_ID}'),
            now()
        );
        RAISE NOTICE 'created target org "${TARGET_ORG_ID}".';
    END IF;

    -- Move all projects from legacy → target.
    UPDATE projects SET org_id = '${TARGET_ORG_ID}' WHERE org_id = '${LEGACY_ORG_ID}';

    -- Move memberships. Delete any legacy-org row whose (user, role) already
    -- exists on the target org; UPDATE the rest. This handles the case where
    -- the second headless-init re-created the admin's membership on the new
    -- org while leaving the old one in place.
    IF memberships_table_exists THEN
        DELETE FROM organization_memberships m_legacy
        WHERE m_legacy.org_id = '${LEGACY_ORG_ID}'
          AND EXISTS (
              SELECT 1 FROM organization_memberships m_target
              WHERE m_target.org_id = '${TARGET_ORG_ID}'
                AND m_target.user_id = m_legacy.user_id
          );
        UPDATE organization_memberships
        SET org_id = '${TARGET_ORG_ID}'
        WHERE org_id = '${LEGACY_ORG_ID}';
    END IF;

    -- Final sanity check: nothing FK'd to the legacy org should remain.
    IF EXISTS (SELECT 1 FROM projects WHERE org_id = '${LEGACY_ORG_ID}') THEN
        RAISE EXCEPTION 'projects still reference legacy org "${LEGACY_ORG_ID}" — aborting.';
    END IF;

    DELETE FROM organizations WHERE id = '${LEGACY_ORG_ID}';
    RAISE NOTICE 'migrated org "${LEGACY_ORG_ID}" → "${TARGET_ORG_ID}".';
END
\$\$;

-- Make sure the project name matches the per-app convention (the compose
-- file already sets the right project id on fresh boots).
UPDATE projects
SET name = '${TARGET_ORG_NAME}'
WHERE id = '${TARGET_PROJECT_ID}' AND name <> '${TARGET_ORG_NAME}';
SQL

echo "==> Done."
echo "    Verify in the UI: https://smagowski-ai-lab-langfuse.duckdns.org"
echo "    Admin user: ${ADMIN_EMAIL:-(set ADMIN_EMAIL via fetch-secrets.sh)}"
