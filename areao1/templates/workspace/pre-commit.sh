#!/bin/sh
# Installed by `areao1 init`: block commits that contain tokens or keys.
if command -v gitleaks >/dev/null 2>&1; then
  if ! gitleaks git --staged --redact --no-banner; then
    echo "areao1: gitleaks found a possible secret in staged changes; commit blocked." >&2
    exit 1
  fi
else
  echo "areao1: gitleaks is not installed, so the secret scan was skipped (https://github.com/gitleaks/gitleaks)." >&2
fi
