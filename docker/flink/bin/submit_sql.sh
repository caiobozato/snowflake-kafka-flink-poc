#!/bin/sh
# Submit the SQL pipeline to the Flink cluster.
#
# Every file in SQL_DIR is concatenated in lexical order and handed to the SQL
# client as one script: table DDL first, then the INSERT statements that become
# the running job. Editing a .sql file and re-running this container is the
# whole development loop.
set -e

SQL_DIR="${SQL_DIR:-/opt/flink/sql}"
JOB_FILE=/tmp/pipeline.sql
REST="${FLINK_REST_URL:-http://flink-jobmanager:8081}"

# Flink SQL has no variable substitution of its own, so the placeholders in the
# .sql files are replaced here. Anything added to a .sql file must be listed.
SUBSTITUTIONS="SOURCE_TOPIC SINK_TOPIC KAFKA_BOOTSTRAP_SERVERS CONSUMER_GROUP SCAN_STARTUP_MODE"

# A job submitted with no free slots sits in SCHEDULED, which looks like a hang.
# Wait for a TaskManager to register instead.
echo "waiting for a TaskManager with a free slot at ${REST}"
slots=""
i=0
while [ "$i" -lt 60 ]; do
  slots=$(curl -sf "${REST}/overview" | sed -n 's/.*"slots-available":\([0-9]*\).*/\1/p' || true)
  if [ -n "$slots" ] && [ "$slots" -gt 0 ]; then
    echo "  ${slots} slot(s) available"
    break
  fi
  i=$((i + 1))
  sleep 2
done
if [ -z "$slots" ] || [ "$slots" -eq 0 ]; then
  echo "no TaskManager slots became available" >&2
  exit 1
fi

# Submitting again would otherwise leave the previous job running alongside the
# new one, both consuming the source and writing the same sink. This cluster
# exists for this one pipeline, so replacing is the useful default; set
# REPLACE_RUNNING_JOBS=false to keep what is already running.
if [ "${REPLACE_RUNNING_JOBS:-true}" = "true" ]; then
  running=$(curl -sf "${REST}/jobs" | tr '{' '\n' \
    | sed -n 's/.*"id":"\([a-f0-9]*\)","status":"RUNNING".*/\1/p' || true)
  for id in $running; do
    echo "cancelling running job ${id}"
    curl -sf -X PATCH "${REST}/jobs/${id}?mode=cancel" -o /dev/null || true
  done
fi

: > "$JOB_FILE"
for f in "$SQL_DIR"/*.sql; do
  [ -f "$f" ] || continue
  echo "-- ---------- $(basename "$f") ----------" >> "$JOB_FILE"
  cat "$f" >> "$JOB_FILE"
  echo "" >> "$JOB_FILE"
done

for name in $SUBSTITUTIONS; do
  value=$(eval "printf '%s' \"\${$name}\"")
  if [ -z "$value" ]; then
    echo "environment variable ${name} is not set" >&2
    exit 1
  fi
  # Values here are topic names and host:port pairs, so | is a safe delimiter.
  sed -i "s|\${${name}}|${value}|g" "$JOB_FILE"
done

if grep -q '\${' "$JOB_FILE"; then
  echo "unresolved placeholders remain; add them to SUBSTITUTIONS:" >&2
  grep -o '\${[A-Z_]*}' "$JOB_FILE" | sort -u >&2
  exit 1
fi

echo "submitting SQL from ${SQL_DIR}:"
sed -n 's/^-- ---------- \(.*\) ----------$/  \1/p' "$JOB_FILE"
exec "${FLINK_HOME}/bin/sql-client.sh" -f "$JOB_FILE"
