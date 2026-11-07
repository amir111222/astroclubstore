#!/bin/bash
# Apply a synced tree at /srv/astrostore/app to the running store.
set -euo pipefail

APP_ROOT=/srv/astrostore/app
DJANGO_DIR="$APP_ROOT/astrostore"
VENV=/srv/astrostore/venv
ENV_FILE=/etc/astrostore.env

if [[ ! -f "$DJANGO_DIR/manage.py" ]]; then
  echo "missing $DJANGO_DIR/manage.py" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE" >&2
  exit 1
fi

chown -R astrostore:astrostore "$APP_ROOT"
# Keep writable media/private media owned by the app user.
chown -R astrostore:astrostore /srv/astrostore/shared/media /srv/astrostore/shared/private_media

if [[ -f "$APP_ROOT/requirements.txt" ]]; then
  if "$VENV/bin/pip" install -q -r "$APP_ROOT/requirements.txt"; then
    echo "dependencies installed"
  else
    echo "pip install skipped or failed (using existing venv)" >&2
  fi
fi

run_django() {
  sudo -u astrostore bash -c "set -a; source '$ENV_FILE'; set +a; cd '$DJANGO_DIR'; '$VENV/bin/python' manage.py $*"
}

run_django migrate --noinput
run_django collectstatic --noinput

if [[ -n "${DEPLOY_SHA:-}" ]]; then
  printf '%s\n' "$DEPLOY_SHA" > "$APP_ROOT/.deploy-revision"
  chown astrostore:astrostore "$APP_ROOT/.deploy-revision"
fi

systemctl restart astrostore
sleep 2
systemctl is-active --quiet astrostore

code="$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: 95.38.234.122' http://127.0.0.1/)"
if [[ "$code" != "200" ]]; then
  echo "health check failed: GET / -> $code" >&2
  journalctl -u astrostore -n 40 --no-pager >&2 || true
  exit 1
fi

echo "deploy ok sha=${DEPLOY_SHA:-unknown} home=$code"
