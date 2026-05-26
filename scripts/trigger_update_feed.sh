#!/bin/zsh
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

REPO="kuanyangdai-droid/aeroview-live-feed"
WORKFLOW="update-feed.yml"
REF="main"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Triggering ${WORKFLOW} on ${REPO}@${REF}"
gh workflow run "${WORKFLOW}" --repo "${REPO}" --ref "${REF}"
