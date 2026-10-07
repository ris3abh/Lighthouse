#!/bin/sh
# Area O1 installer for macOS and Linux (ADR 0013). Read it before you run it:
#
#   curl -LsSf https://raw.githubusercontent.com/ris3abh/areao1/main/install.sh | sh
#
# It installs uv (Astral's Python tool manager) if you don't have it, installs Area O1 as a uv tool
# on Python 3.12, then starts Area O1. It makes no other change to your machine.
#
#   AREAO1_SPEC=<wheel file or URL>   install this instead of the latest release
#   AREAO1_NO_RUN=1                   install only; don't start Area O1
set -eu

repo=ris3abh/areao1

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv (https://docs.astral.sh/uv/) ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
fi

spec=${AREAO1_SPEC:-}
if [ -z "$spec" ]; then
  spec=$(curl -fsSL "https://api.github.com/repos/$repo/releases/latest" | grep -o 'https://[^"]*\.whl' | head -n 1)
  [ -n "$spec" ] || { echo "No Area O1 release found at https://github.com/$repo/releases" >&2; exit 1; }
fi

echo "Installing Area O1 from $spec ..."
uv tool install --force --python 3.12 "$spec"  # uv says if its tool folder isn't on your PATH

if [ "${AREAO1_NO_RUN:-}" = 1 ]; then
  echo "Installed. Start Area O1 any time with: areao1"
  exit 0
fi
echo "Starting Area O1 (Ctrl+C stops it; run 'areao1' to start it again) ..."
exec "$(uv tool dir --bin)/areao1"
