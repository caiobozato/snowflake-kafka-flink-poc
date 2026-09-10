#!/bin/sh
# The base image declares /opt/nifi/nifi-current/conf as a VOLUME, and Compose
# preserves anonymous volumes when it recreates a container. That means a stale
# conf directory can outlive an image rebuild: JVM arguments added at build time
# would not take effect, and the self-signed certificate would keep the
# SubjectAltName of whichever container generated it first, which fails Jetty's
# SNI check from other containers.
#
# Restoring conf from the image on every boot keeps the container reproducible.
# The flow itself is not lost: it is rebuilt from build_flow.py.
set -e

if [ -d /opt/nifi/conf-template ]; then
  rm -rf /opt/nifi/nifi-current/conf/*
  cp -a /opt/nifi/conf-template/. /opt/nifi/nifi-current/conf/
fi

exec /opt/nifi/scripts/start.sh
