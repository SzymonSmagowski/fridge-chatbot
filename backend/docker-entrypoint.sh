#!/bin/sh
set -e

exec poetry run uvicorn server:app --host 0.0.0.0 --port 8001 --log-level info --access-log
