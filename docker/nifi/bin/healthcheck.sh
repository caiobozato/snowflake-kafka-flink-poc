#!/bin/sh
# NiFi serves the UI without authentication; the API behind it needs a token.
# A 200 here means the web layer is up, which is what dependants wait on.
exec curl -ksf -o /dev/null "https://localhost:${NIFI_WEB_HTTPS_PORT:-8443}/nifi/"
