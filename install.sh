#!/bin/sh
# Lighthouse installer for macOS and Linux (ADR 0013). Read it before you run it:
#
#   curl -LsSf https://raw.githubusercontent.com/ris3abh/Lighthouse/main/install.sh | sh
#
# It installs uv (Astral's Python tool manager) if you don't have it, installs Lighthouse as a uv tool
# on Python 3.12, then starts Lighthouse. It makes no other change to your machine.
#
#   LIGHTHOUSE_GC_SPEC=<wheel file or URL>   install this instead of the latest release
#   LIGHTHOUSE_GC_NO_RUN=1                   install only; don't start Lighthouse
set -eu

repo=ris3abh/Lighthouse

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv (https://docs.astral.sh/uv/) ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
fi

spec=${LIGHTHOUSE_GC_SPEC:-}
if [ -z "$spec" ]; then
  spec=$(curl -fsSL "https://api.github.com/repos/$repo/releases/latest" | grep -o 'https://[^"]*\.whl' | head -n 1)
  [ -n "$spec" ] || { echo "No Lighthouse release found at https://github.com/$repo/releases" >&2; exit 1; }
fi

echo "Installing Lighthouse from $spec ..."
uv tool install --force --python 3.12 "$spec"  # uv says if its tool folder isn't on your PATH

if [ "${LIGHTHOUSE_GC_NO_RUN:-}" = 1 ]; then
  echo "Installed. Start Lighthouse any time with: lighthouse-gc"
  exit 0
fi
echo "Starting Lighthouse (Ctrl+C stops it; run 'lighthouse-gc' to start it again) ..."
exec "$(uv tool dir --bin)/lighthouse-gc"
