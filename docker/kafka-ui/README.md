# kafka-ui

Web UI for the broker: browse topics and messages, inspect consumer groups and
their lag, manage schemas, view broker configuration.

Open http://localhost:8090 (`KAFKA_UI_PORT`).

Runs [kafbat/kafka-ui](https://github.com/kafbat/kafka-ui) `v1.5.0` — the
maintained community fork of provectus/kafka-ui, which stopped at `v0.7.2`. The
config schema is unchanged between them.

It talks to Redpanda over the plain Kafka API and Schema Registry API, so no
Redpanda-specific wiring is involved. On startup it reports the cluster as
`ONLINE` with the `SCHEMA_REGISTRY`, `TOPIC_DELETION`, `KAFKA_ACL_VIEW` and
`FTS_ENABLED` features detected.

There is no auth in front of it, and it has full admin access to the broker —
topic creation and deletion included — so keep it bound to localhost.

## Configuration

`config/kafka-ui.yaml` is mounted read-only at `/etc/kafkaui/kafka-ui.yaml` and
loaded through `SPRING_CONFIG_ADDITIONALLOCATION`. A file rather than a wall of
`KAFKA_CLUSTERS_0_*` environment variables, so the wiring is reviewable in one
place.

It sets:

- `kafka.clusters[0].bootstrapServers` — `redpanda:9092`
- `kafka.clusters[0].schemaRegistry` — `http://redpanda:8081`
- `auth.type: DISABLED` — no login screen
- `dynamic.config.enabled: true` — clusters can be added or edited from the UI
- `server.max-http-request-header-size: 64KB` — see Troubleshooting below

Adding a second cluster later means another entry under `kafka.clusters`. The
config is read once at startup, and Compose does not notice edits to a
bind-mounted file, so `docker compose up -d` will *not* pick them up:

```bash
docker compose restart kafka-ui
```

## Troubleshooting

**Blank page or an error in the browser while `curl` works.** Almost certainly
oversized request headers. Netty caps them at 8KB by default, and a browser
easily exceeds that on `localhost`, where cookies accumulate across every dev
tool you have ever run on any port. Every request then returns `431 Request
Header Fields Too Large` — invisible in the container healthcheck, which passes,
because `wget` and `curl` send no cookies.

`server.max-http-request-header-size: 64KB` in `config/kafka-ui.yaml` raises the
limit. Reproduce and confirm from the shell:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Cookie: a=$(python3 -c "print('x'*9000)")" http://localhost:8090/
```

`200` means the limit is in effect; `431` means the container is running with the
old config — `docker compose restart kafka-ui`. Clearing cookies for
`localhost` also works, but they will build up again.

**Healthcheck fails after an image bump while the UI works.** Check
`/actuator/health` for a probe with no backing service here — on provectus
`v0.7.2` the LDAP probe reported `DOWN` and had to be switched off with
`management.health.ldap.enabled: false`. Not needed on `v1.5.0`.

## Environment variables

| Variable        | Default | Purpose |
| --------------- | ------- | ------- |
| `KAFKA_UI_PORT` | `8090`  | Host port for the UI. |

## Useful HTTP endpoints

Handy for scripting, or for checking the UI is wired up without a browser:

```bash
curl -s http://localhost:8090/actuator/health            # {"status":"UP"}
curl -s http://localhost:8090/api/clusters               # cluster status + detected features
curl -s "http://localhost:8090/api/clusters/local/topics?showInternal=true"
curl -s http://localhost:8090/api/clusters/local/schemas

# message browsing (server-sent events)
curl -s "http://localhost:8090/api/clusters/local/topics/<topic>/messages/v2?mode=EARLIEST&limit=1"
```

Note the `/messages/v2` path with `mode=`. kafbat retired the provectus-era
`/messages?seekDirection=FORWARD` endpoint, which now answers
`4002 Not supported` — worth knowing if you copy a snippet from older docs.

Topic counts and sizes come from a statistics scheduler that refreshes
periodically, so a brand-new topic can take a moment to appear in list
responses even though it is immediately usable.
