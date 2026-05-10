#!/usr/bin/env bash
# Idempotent downloader for openWakeWord ONNX models.
#
# openWakeWord ships its model files via the GitHub release of the Python
# package: melspectrogram, embedding, and one classifier per wake word. We
# pull them directly from raw.githubusercontent.com so there's no Python /
# pip dependency in the frontend dev loop.
#
# Files land in `public/wake-words/` and are gitignored. ~11MB total.
# Runs from `dev.sh` on first start; safe to re-run (skips files that exist).
set -euo pipefail

DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/public/wake-words"
mkdir -p "$DEST"

# Pinned to the openWakeWord release that ships the prebuilt ONNX models as
# release attachments (v0.5.1 — later releases drop the files because
# they're large). Bumping this version requires re-validating the
# input/output tensor shapes in wake-word-pipeline.ts; they're encoded into
# the inference loop.
TAG="v0.5.1"
BASE="https://github.com/dscripka/openWakeWord/releases/download/${TAG}"

FILES=(
  "melspectrogram.onnx"     # mel-spectrogram preprocessing
  "embedding_model.onnx"    # Google speech embedding (~9MB)
  "hey_jarvis_v0.1.onnx"    # the wake-word classifier (~50KB)
)

ok=true
for f in "${FILES[@]}"; do
  if [[ -f "$DEST/$f" ]]; then
    echo "  ✓ $f (cached)"
    continue
  fi
  echo "  ↓ $f"
  if ! curl -fsSL "$BASE/$f" -o "$DEST/$f"; then
    echo "    failed to fetch $BASE/$f" >&2
    rm -f "$DEST/$f"
    ok=false
  fi
done

if ! $ok; then
  echo "" >&2
  echo "Wake-word model download failed. The kiosk still works (mic-tap" >&2
  echo "fallback), but the 'hey jarvis' passive listener will be disabled" >&2
  echo "until the next successful download." >&2
  exit 1
fi

echo "Wake-word models in $DEST"
ls -lh "$DEST"/*.onnx 2>/dev/null | awk '{ printf "  %-32s %s\n", $9, $5 }'
