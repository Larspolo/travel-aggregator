#!/bin/bash
# The check of the deployed preview (verify level 5, at the end of an epic). It waits until
# https://travel-preview.larspolo.nl runs the commit (default: origin/main), then tests the API with the token of the
# network secret of the cloud environment (the proxy adds "Authorization: Bearer ..." to each request to the host; the
# script never sees the token). It makes one trip "agent check <time>" with one offer: the preview has test data only.
# The pages are behind Traefik basic auth and the login: test them locally (verify levels 2 and 4).
# Usage: scripts/preview_check.sh [COMMIT]   (PREVIEW_URL overrides the host)
set -euo pipefail
url=${PREVIEW_URL:-https://travel-preview.larspolo.nl}
want=${1:-$(git rev-parse origin/main)}
json() { python3 -c "import json, sys; print(json.load(sys.stdin)$1)"; }

got=
for _ in $(seq 60); do        # CI with its job preview, then watchtower: about 10 minutes, at most 15
  got=$(curl -fsS "$url/api/health" 2>/dev/null | json '["commit"]' 2>/dev/null) || got=   # empty while it restarts
  [ "$got" = "$want" ] && break
  sleep 15
done
[ "$got" = "$want" ] || { echo "FAIL health: the preview runs '${got:-nothing}', not $want"; exit 1; }
echo "ok   health: commit $got"

code=$(curl -s -o /dev/null -w '%{http_code}' "$url/api/trips")
if [ "$code" != 200 ]; then
  echo "FAIL GET /api/trips: HTTP $code (401: the environment has no network secret for ${url#https://})"; exit 1
fi
trip=$(curl -fsS -H 'Content-Type: application/json' -d "{\"title\": \"agent check $(date -u +%FT%TZ)\"}" \
  "$url/api/trips" | json '["id"]')
body=$(python3 -c "import json, sys; print(json.dumps({'trip_id': int(sys.argv[1]), 'source': 'agent-check',
  'captured_at': '2026-11-06T10:00:00Z', 'offers': [{'price_amount': '42.00', 'price_currency': 'EUR',
  'legs': [{'mode': 'train', 'carrier': 'TEST', 'service_no': 'T 1', 'from_name': 'A', 'to_name': 'B',
  'depart_at': '2026-12-20T07:00:00+01:00', 'arrive_at': '2026-12-20T09:00:00+01:00'}]}]}))" "$trip")
created=$(curl -fsS -H 'Content-Type: application/json' -d "$body" "$url/api/ingest" | json '["created"]')
[ "$created" = 1 ] || { echo "FAIL POST /api/ingest: created $created, not 1"; exit 1; }
echo "ok   api: trip $trip with one offer"
