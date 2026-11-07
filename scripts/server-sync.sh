#!/bin/bash
# Pull the latest GitHub main branch and apply it to the live store.
set -euo pipefail

REPO_URL="https://github.com/amir111222/astroclubstore.git"
SRC=/srv/astrostore/src
APP=/srv/astrostore/app
BRANCH=main
LOCK=/run/astrostore-sync.lock

mkdir -p /run
exec 9>"$LOCK"
if ! flock -n 9; then
  exit 0
fi

if [[ ! -d "$SRC/.git" ]]; then
  git clone --depth 50 --branch "$BRANCH" "$REPO_URL" "$SRC"
fi

cd "$SRC"
git remote set-url origin "$REPO_URL"
git fetch --quiet --depth 50 origin "$BRANCH"
REMOTE="$(git rev-parse "origin/$BRANCH")"
LOCAL="$(git rev-parse HEAD)"
DEPLOYED=""
if [[ -f "$APP/.deploy-revision" ]]; then
  DEPLOYED="$(tr -d '[:space:]' < "$APP/.deploy-revision")"
fi

if [[ "$REMOTE" == "$DEPLOYED" ]]; then
  exit 0
fi

git checkout -q -f "$BRANCH"
git reset --hard "origin/$BRANCH"
git clean -fdq -e '.deploy-revision'

rsync -a --delete \
  --exclude '.git/' \
  --exclude '.github/' \
  --exclude '.venv/' \
  --exclude 'node_modules/' \
  --exclude 'graphify-out/' \
  --exclude 'astrostore/media/' \
  --exclude 'astrostore/staticfiles/' \
  --exclude 'astrostore/private_media/' \
  --exclude 'private_media/' \
  --exclude '.env' \
  --exclude '.deployment-*' \
  "$SRC/" "$APP/"

chmod +x "$APP/scripts/server-deploy.sh" "$APP/scripts/server-sync.sh"
install -m 755 "$APP/scripts/server-deploy.sh" /usr/local/sbin/astrostore-deploy.sh
install -m 755 "$APP/scripts/server-sync.sh" /usr/local/sbin/astrostore-sync.sh

DEPLOY_SHA="$REMOTE" /usr/local/sbin/astrostore-deploy.sh
echo "synced $REMOTE"
