#!/bin/bash
# Run a command up to 3 times, 10 s apart, for the image pulls of CI: Docker Hub sometimes answers 502 or resets the
# connection, and the owner then started the CI run again by hand (#509, #615). Use it only for a pull: a build or
# start error must fail at once. The exit code is that of the last try. RETRY_SLEEP changes the wait (the tests).
# Usage: scripts/retry.sh CMD [ARG...]
for i in 1 2; do
  "$@" && exit 0
  echo "retry.sh: try $i of 3 failed: $*" >&2
  sleep "${RETRY_SLEEP:-10}"
done
exec "$@"
