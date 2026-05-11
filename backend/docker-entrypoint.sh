#!/bin/sh
set -e

# In the production image the venv at /app/.venv is on PATH (Dockerfile sets it),
# so `uvicorn` resolves directly. No `poetry run` — Poetry isn't in the runtime stage.
exec uvicorn server:app --host 0.0.0.0 --port 8001 --log-level info --access-log
